# Copyright (C) 2022 Zijun Yang <zijun.yang@outlook.com>
#
# This file is part of God of Avalon Backend.
#
# God of Avalon Backend is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# God of Avalon Backend is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with God of Avalon Backend.  If not, see <http://www.gnu.org/licenses/>.

import json
import random

from django.db import transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token

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
        return json.loads(request.body.decode("utf-8"))
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


def create_room(request):
    body = parse_body(request)
    roomid = body.get("roomid", "")
    if not roomid:
        return fail("roomid_empty")
    if len(roomid) > 6:
        return fail("roomid_long")
    if get_room(roomid):
        return fail("roomid_taken")
    Room.objects.create(roomid=roomid)
    return ok()


def join_room(request):
    body = parse_body(request)
    roomid, userid, userpsw = body.get("roomid"), body.get("userid"), body.get("userpsw")
    room = get_room(roomid)
    if not room:
        return fail("room_not_found")
    if len(userid or "") > 7 or len(userpsw or "") > 6:
        return fail("id_or_psw_long")

    avatar = body.get("avatar", "")

    existing = room.players.filter(userid=userid).first()
    if existing:
        if existing.userpsw == userpsw:
            # A player's first avatar is permanent. Return the stored filename so
            # a re-login can restore the correct localStorage value.
            return ok(created=False, avatar=existing.avatar)
        return fail("wrong_password")
    if room.status != Room.Status.WAITING:
        return fail("room_started")
    player = room.players.create(userid=userid, userpsw=userpsw, avatar=avatar)
    return ok(created=True, avatar=player.avatar)


def waiting_room(request):
    player = load_player(parse_body(request))
    if not player:
        return fail("bad_credentials")
    room = player.room
    players = list(room.players.order_by("id"))
    users = [p.userid for p in players]
    avatars = {p.userid: p.avatar for p in players}
    return ok(roomstatus=room.status, users=users, avatars=avatars)


def start_game(request):
    body = parse_body(request)
    player = load_player(body)
    if not player:
        return fail("bad_credentials")
    room = player.room
    if room.status == Room.Status.STARTED:
        return fail("already_started")
    count = room.players.count()
    roles = TEMPLATES.get(count)
    if roles is None:
        return fail("bad_players_count")
    deck = list(roles)
    random.shuffle(deck)
    for other in room.players.order_by("id"):
        other.role = deck.pop()
        other.save()
    room.status = Room.Status.STARTED
    room.save()
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
