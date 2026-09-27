import json
import random
import re

from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.http import require_POST

from .avatars import AVATARS

from .models import (
    TEMPLATES,
    VISIBLE_WHAT,
    Player,
    Room,
    Vote,
)


# ---- helpers ------------------------------------------------------------------


def ok(**kwargs):
    """Structured success response: {"ok": True, **payload}."""
    data = {"ok": True}
    data.update(kwargs)
    return JsonResponse(data)


def fail(message):
    """Structured error response: {"ok": False, "message": ...}."""
    return JsonResponse({"ok": False, "message": message})


def parse_body(request):
    """Read and decode a JSON request body (tolerant of empty/malformed input)."""
    try:
        body = json.loads(request.body.decode("utf-8"))
        return body if isinstance(body, dict) else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def load_player(body):
    """Resolve {roomid,userid,userpsw} from a body to a Player (or None)."""
    return Player.objects.filter(
        room__roomid=body.get("roomid"),
        userid=body.get("userid"),
        userpsw=body.get("userpsw"),
    ).select_related("room").first()


def get_room(roomid):
    return Room.objects.filter(roomid=roomid).first()


# ---- public endpoints ----------------------------------------------------------


def get_csrf_token(request):
    return JsonResponse({"token": get_token(request)})


def room_status(request, roomid):
    """Credential-free room lookup (used only to decide waiting vs in-room routing)."""
    room = get_room(roomid)
    if not room:
        return fail("room_not_found")
    return ok(status=room.status)


@require_POST
def create_room(request):
    body = parse_body(request)
    roomid = body.get("roomid", "")
    if not isinstance(roomid, str) or not roomid:
        return fail("roomid_empty")
    if len(roomid) > 6:
        return fail("roomid_long")
    if not re.fullmatch(r"[A-Za-z0-9]{1,6}", roomid):
        return fail("bad_roomid")
    try:
        with transaction.atomic():
            Room.objects.create(roomid=roomid)
    except IntegrityError:
        return fail("roomid_taken")
    return ok()


def lock_room(roomid, create=False):
    # A write first serializes join/start/avatar changes on SQLite. The row lock
    # also covers databases supporting SELECT FOR UPDATE.
    Room.objects.filter(roomid=roomid).update(status=F("status"))
    if create:
        Room.objects.get_or_create(roomid=roomid)
    return Room.objects.select_for_update().filter(roomid=roomid).first()


def enter_room(body, create=False):
    roomid, userid, userpsw = body.get("roomid"), body.get("userid"), body.get("userpsw")
    for value, pattern, error in (
        (roomid, r"[A-Za-z0-9]{1,6}", "bad_roomid"),
        (userid, r"[A-Za-z0-9_]{1,7}", "bad_userid"),
        (userpsw, r"[A-Za-z0-9]{1,6}", "bad_password"),
    ):
        if not isinstance(value, str) or not re.fullmatch(pattern, value):
            return fail(error)
    avatar = body.get("avatar", "")
    if not isinstance(avatar, str) or avatar not in AVATARS:
        avatar = AVATARS[0]

    with transaction.atomic():
        room = lock_room(roomid, create=create)
        if not room:
            return fail("room_not_found")
        existing = room.players.filter(userid=userid).first()
        if existing:
            if existing.userpsw != userpsw:
                return fail("wrong_password")
            return ok(created=False, avatar=existing.avatar, roomstatus=room.status)
        if room.status != Room.Status.WAITING:
            return fail("room_started")
        if room.players.count() >= max(TEMPLATES):
            return fail("room_full")
        player = room.players.create(userid=userid, userpsw=userpsw, avatar=avatar)
        return ok(created=True, avatar=player.avatar, roomstatus=room.status)


@require_POST
def create_or_join_room(request):
    # The room and its first player commit together. All players requesting the
    # same next ID join this room, including simultaneous first arrivals.
    return enter_room(parse_body(request), create=True)


@require_POST
def join_room(request):
    return enter_room(parse_body(request))


@require_POST
def set_avatar(request):
    body = parse_body(request)
    avatar = body.get("avatar")
    if not isinstance(avatar, str) or avatar not in AVATARS:
        return fail("bad_avatar")
    player = load_player(body)
    if not player:
        return fail("bad_credentials")
    with transaction.atomic():
        room = lock_room(player.room.roomid)
        if not room:
            return fail("room_not_found")
        if room.status != Room.Status.WAITING:
            return fail("not_waiting")
        player.avatar = avatar
        player.save(update_fields=["avatar"])
        return ok(avatar=avatar, avatars=dict(room.players.values_list("userid", "avatar")))


def waiting_room(request):
    player = load_player(parse_body(request))
    if not player:
        return fail("bad_credentials")
    room = player.room
    players = list(room.players.order_by("id"))
    users = [p.userid for p in players]
    avatars = {p.userid: p.avatar for p in players}
    return ok(roomstatus=room.status, users=users, avatars=avatars)


@require_POST
def start_game(request):
    body = parse_body(request)
    player = load_player(body)
    if not player:
        return fail("bad_credentials")
    with transaction.atomic():
        room = lock_room(player.room.roomid)
        if not room:
            return fail("room_not_found")
        if room.status == Room.Status.STARTED:
            return fail("already_started")
        players = list(room.players.order_by("id"))
        roles = TEMPLATES.get(len(players))
        if roles is None:
            return fail("bad_players_count")
        deck = list(roles)
        random.shuffle(deck)
        for other in players:
            other.role = deck.pop()
        Player.objects.bulk_update(players, ["role"])
        room.status = Room.Status.STARTED
        room.save(update_fields=["status"])
    return ok()


def my_role(request):
    body = parse_body(request)
    player = load_player(body)
    if not player:
        return fail("bad_credentials")
    room = player.room
    if room.status != Room.Status.STARTED:
        return fail("not_started")
    visible = VISIBLE_WHAT.get(player.role, set())
    seen_players = [
        other
        for other in room.players.exclude(pk=player.pk)
        if other.role in visible
    ]
    seen = [other.userid for other in seen_players]
    avatars = {other.userid: other.avatar for other in seen_players}
    return ok(role=player.role, users=seen, avatars=avatars)


def room_state(request):
    body = parse_body(request)
    player = load_player(body)
    if not player:
        return fail("bad_credentials")
    room = player.room
    if room.status != Room.Status.STARTED:
        return fail("not_started")
    members = [p.userid for p in room.players.filter(on_vote=True)]
    return ok(
        phase=room.phase,
        team_builder=room.team_builder.userid if room.team_builder else "",
        members=members,
        on_vote=player.on_vote,
        voted=player.voted,
        build_round=room.votes.filter(kind=Vote.Kind.BUILD).count() + 1,
        quest_round=room.votes.filter(kind=Vote.Kind.QUEST).count() + 1,
    )


def build_team(request):
    body = parse_body(request)
    player = load_player(body)
    if not player:
        return fail("bad_credentials")
    room = player.room
    if room.status != Room.Status.STARTED:
        return fail("not_started")
    if room.phase != Room.Phase.NORMAL:
        return fail("vote_in_progress")

    members = body.get("members", [])
    if not isinstance(members, list) or len(members) < 2:
        return fail("team_too_small")
    if len(members) != len(set(members)):
        return fail("dup_members")
    for userid in members:
        if not room.players.filter(userid=userid).exists():
            return fail("member_not_found")

    # reset everyone's membership + ballots, then mark the chosen team
    room.players.update(on_vote=False, voted=False)
    room.players.filter(userid__in=members).update(on_vote=True)
    room.team_builder = player
    room.phase = Room.Phase.BUILD
    room.save()
    return ok()


class VoteError(Exception):
    """Signal that a ballot is invalid; rolled back and surfaced to the client."""


def vote(request):
    body = parse_body(request)
    player = load_player(body)
    if not player:
        return fail("bad_credentials")
    if player.room.status != Room.Status.STARTED:
        return fail("not_started")

    choice = bool(body.get("choice", True))

    try:
        # The read-modify-write touches several rows (this player's ballot, then
        # the whole-room quorum + a new Vote row). It must be one atomic unit so
        # two near-simultaneous ballots can't both see quorum and double-resolve
        # a phase (which produced a phantom duplicate Vote row + inconsistent flags).
        with transaction.atomic():
            # SQLite has no row-level locking: `select_for_update` is a no-op and
            # a read-first transaction then fails to upgrade to a write lock when a
            # concurrent vote holds a shared read lock ("database is locked", 500).
            # So make the FIRST statement a write: it grabs SQLite's exclusive
            # write lock up-front and later votes simply queue on it (busy timeout),
            # serializing every ballot for the game.
            changed = Player.objects.filter(pk=player.pk).update(voted=True, result=choice)

            room = Room.objects.get(pk=player.room_id)
            if not changed or room.status != Room.Status.STARTED:
                raise VoteError("bad_credentials")
            if room.phase == Room.Phase.NORMAL:
                raise VoteError("no_vote")
            if player.voted:  # already cast a ballot this phase -> roll back the write
                raise VoteError("already_voted")

            if room.phase == Room.Phase.BUILD:
                voted_total = room.players.count()
                voted_now = room.players.filter(voted=True).count()
            else:  # QUEST
                voted_total = room.players.filter(on_vote=True).count()
                voted_now = room.players.filter(on_vote=True, voted=True).count()

            if room.phase == Room.Phase.BUILD and voted_now == voted_total:
                members = [p.userid for p in room.players.filter(on_vote=True)]
                agree = room.players.filter(voted=True, result=True).count()
                disagree = room.players.filter(voted=True, result=False).count()
                ballots = [
                    {"userid": p.userid, "choice": p.result}
                    for p in room.players.filter(voted=True)
                ]
                Vote.objects.create(
                    room=room,
                    kind=Vote.Kind.BUILD,
                    round_no=room.votes.filter(kind=Vote.Kind.BUILD).count() + 1,
                    builder=room.team_builder,
                    members=members,
                    agree=agree,
                    disagree=disagree,
                    ballots=ballots,
                )
                if agree > disagree:
                    room.phase = Room.Phase.QUEST
                    room.players.update(voted=False)
                else:
                    room.phase = Room.Phase.NORMAL
                room.save()
            elif room.phase == Room.Phase.QUEST and voted_now == voted_total:
                members = [p.userid for p in room.players.filter(on_vote=True)]
                agree = room.players.filter(on_vote=True, voted=True, result=True).count()
                disagree = room.players.filter(on_vote=True, voted=True, result=False).count()
                ballots = [
                    {"userid": p.userid, "choice": p.result}
                    for p in room.players.filter(on_vote=True, voted=True)
                ]
                Vote.objects.create(
                    room=room,
                    kind=Vote.Kind.QUEST,
                    round_no=room.votes.filter(kind=Vote.Kind.QUEST).count() + 1,
                    builder=room.team_builder,
                    members=members,
                    agree=agree,
                    disagree=disagree,
                    ballots=ballots,
                )
                room.phase = Room.Phase.NORMAL
                room.save()
            return ok()
    except VoteError as e:
        return fail(str(e))


def history(request):
    body = parse_body(request)
    player = load_player(body)
    if not player:
        return fail("bad_credentials")
    room = player.room
    votes = [
        {
            "kind": v.kind,
            "round_no": v.round_no,
            "builder": v.builder.userid if v.builder else "",
            "members": v.members,
            "agree": v.agree,
            "disagree": v.disagree,
            "ballots": v.ballots,
        }
        for v in room.votes.order_by("id")
    ]
    avatars = {p.userid: p.avatar for p in room.players.all()}
    return ok(votes=votes, avatars=avatars)
