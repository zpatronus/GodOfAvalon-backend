from django.db import models

# Roles are stored in the database as stable *codes*, never display strings,
# so the frontend is free to render/label/localize them however it wants.
ROLE_CODES = (
    "merlin",
    "percival",
    "morgana",
    "assassin",
    "loyal_servant",
    "oberon",
    "mordred",
    "minion",
)

ROLE_CHOICES = [(code, code) for code in ROLE_CODES]

# Board composition for each valid player count (5 to 10).
# The Nth element is the role dealt to the Nth player; the list shuffles at start_game.
TEMPLATES = {
    5: ["merlin", "percival", "morgana", "assassin", "loyal_servant"],
    6: ["merlin", "percival", "morgana", "assassin", "loyal_servant", "loyal_servant"],
    7: ["merlin", "percival", "morgana", "assassin", "loyal_servant", "loyal_servant", "oberon"],
    8: ["merlin", "percival", "morgana", "assassin", "loyal_servant", "loyal_servant", "loyal_servant", "mordred"],
    9: ["merlin", "percival", "morgana", "assassin", "mordred", "loyal_servant", "loyal_servant", "loyal_servant", "loyal_servant"],
    10: ["merlin", "percival", "morgana", "assassin", "mordred", "loyal_servant", "loyal_servant", "loyal_servant", "loyal_servant", "minion"],
}

# Which roles a given role can *see* at reveal time. Mirrors the original game rules.
VISIBLE_WHAT = {
    "merlin": {"morgana", "assassin", "minion", "oberon"},
    "percival": {"merlin", "morgana"},
    "assassin": {"assassin", "morgana", "mordred", "minion"},
    "morgana": {"assassin", "morgana", "mordred", "minion"},
    "mordred": {"assassin", "morgana", "mordred", "minion"},
    "minion": {"assassin", "morgana", "mordred", "minion"},
    "loyal_servant": set(),
    "oberon": set(),
}


class Room(models.Model):
    class Status(models.TextChoices):
        WAITING = "waiting"
        STARTED = "started"

    class Phase(models.TextChoices):
        NORMAL = "normal"
        BUILD = "build"
        QUEST = "quest"

    roomid = models.CharField(max_length=6, unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.WAITING)
    phase = models.CharField(max_length=10, choices=Phase.choices, default=Phase.NORMAL)
    team_builder = models.ForeignKey(
        "Player", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)


class Player(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="players")
    userid = models.CharField(max_length=7)
    userpsw = models.CharField(max_length=6)
    # avatar asset file name (e.g. "demon-devil-halloween-lucifer-satan.svg").
    # The room snapshot is authoritative. Players may change this while waiting.
    avatar = models.CharField(max_length=100, blank=True, default="")
    role = models.CharField(max_length=20, blank=True, default="", choices=ROLE_CHOICES)
    # True when this player is a member of the current proposed team / active quest
    on_vote = models.BooleanField(default=False)
    voted = models.BooleanField(default=False)
    # True = approve/success, False = reject/fail (for the most recent ballot)
    result = models.BooleanField(default=False)

    class Meta:
        unique_together = ("room", "userid")


class Vote(models.Model):
    class Kind(models.TextChoices):
        BUILD = "build"
        QUEST = "quest"

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="votes")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    # build: proposal number; quest: quest number
    round_no = models.IntegerField()
    builder = models.ForeignKey(
        "Player", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # ids of the team members (list, so it survives player/team reshuffles)
    members = models.JSONField(default=list)
    # build: approvals; quest: successes
    agree = models.IntegerField(default=0)
    # build: rejections; quest: failures
    disagree = models.IntegerField(default=0)
    # per-player ballot: [{"userid": ..., "choice": true|false}, ...]
    ballots = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
