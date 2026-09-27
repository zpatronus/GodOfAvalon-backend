from unittest.mock import patch

from django.test import TestCase

from .avatars import AVATARS
from .models import Player, Room, TEMPLATES


class RoomEntryTests(TestCase):
    credentials = {"roomid": "abc999", "userid": "Arthur", "userpsw": "1234"}

    def post(self, path="create_or_join_room", **changes):
        return self.client.post(
            f"/{path}/", {**self.credentials, "avatar": AVATARS[0], **changes},
            content_type="application/json",
        ).json()

    def test_create_join_and_reconnect_preserve_identity(self):
        first = self.post()
        self.assertTrue(first["created"])
        self.assertEqual(first["roomstatus"], "waiting")
        self.assertTrue(self.post(userid="Knight")["ok"])
        again = self.post(avatar=AVATARS[1])
        self.assertFalse(again["created"])
        self.assertEqual(again["avatar"], AVATARS[0])
        self.assertEqual(Room.objects.count(), 1)
        self.assertEqual(Player.objects.count(), 2)

    def test_wrong_password_cannot_replace_player(self):
        self.post()
        self.assertEqual(self.post(userpsw="4321", avatar=AVATARS[1])["message"], "wrong_password")
        self.assertEqual(Player.objects.get().avatar, AVATARS[0])

    def test_started_room_only_allows_existing_players(self):
        self.post()
        Room.objects.update(status=Room.Status.STARTED)
        self.assertEqual(self.post()["roomstatus"], "started")
        self.assertEqual(self.post(userid="New")["message"], "room_started")
        self.assertEqual(Player.objects.count(), 1)

    def test_room_capacity_still_allows_reconnect(self):
        for i in range(10):
            self.assertTrue(self.post(userid=f"User{i}")["ok"])
        self.assertEqual(self.post(userid="Extra")["message"], "room_full")
        self.assertTrue(self.post(userid="User0")["ok"])

    def test_validation_happens_before_creating_room(self):
        for fields in ({"roomid": ""}, {"roomid": "bad/id"}, {"roomid": []},
                       {"userid": ""}, {"userid": "a b"}, {"userid": 42},
                       {"userpsw": ""}, {"userpsw": "1234567"}, {"userpsw": {}}):
            with self.subTest(fields=fields):
                self.assertFalse(self.post(**fields)["ok"])
        self.assertEqual(Room.objects.count(), 0)

    def test_room_and_first_player_are_atomic(self):
        with patch.object(Player, "save", side_effect=RuntimeError("simulated failure")):
            with self.assertRaises(RuntimeError):
                self.post()
        self.assertEqual(Room.objects.count(), 0)

    def test_invalid_avatar_gets_safe_default_on_entry(self):
        self.assertEqual(self.post(avatar="../../bad.svg")["avatar"], AVATARS[0])

    def test_next_room_converges_without_changing_previous_game(self):
        self.post()
        self.post(userid="Knight")
        old_room = Room.objects.get()
        old_room.status = Room.Status.STARTED
        old_room.save()
        self.assertTrue(self.post(roomid="abdaaa")["created"])
        self.assertTrue(self.post(roomid="abdaaa", userid="Knight")["created"])
        self.assertFalse(self.post(roomid="abdaaa")["created"])
        self.assertEqual(Room.objects.count(), 2)
        self.assertEqual(Room.objects.get(roomid="abdaaa").players.count(), 2)
        old_room.refresh_from_db()
        self.assertEqual(old_room.status, Room.Status.STARTED)
        self.assertEqual(old_room.players.count(), 2)

    def test_legacy_join_does_not_create_missing_room(self):
        self.assertEqual(self.post("join_room")["message"], "room_not_found")
        self.assertEqual(Room.objects.count(), 0)

    def test_avatar_change_is_authenticated_and_visible_to_other_players(self):
        self.post()
        self.post(userid="Knight")
        self.assertEqual(self.post("set_avatar", userpsw="wrong", avatar=AVATARS[1])["message"], "bad_credentials")
        self.assertTrue(self.post("set_avatar", avatar=AVATARS[1])["ok"])
        snapshot = self.post("waiting_room", userid="Knight")
        self.assertEqual(snapshot["avatars"]["Arthur"], AVATARS[1])
        self.assertEqual(snapshot["avatars"]["Knight"], AVATARS[0])
        self.assertEqual(self.post()["avatar"], AVATARS[1])

    def test_avatar_cannot_change_after_start_or_to_unknown_filename(self):
        self.post()
        self.assertEqual(self.post("set_avatar", avatar="bad.svg")["message"], "bad_avatar")
        Room.objects.update(status=Room.Status.STARTED)
        self.assertEqual(self.post("set_avatar", avatar=AVATARS[1])["message"], "not_waiting")
        self.assertEqual(Player.objects.get().avatar, AVATARS[0])

    def test_start_deals_once_and_locks_avatar_changes(self):
        self.post()
        for i in range(4):
            self.post(userid=f"User{i}")
        self.assertTrue(self.post("start_game")["ok"])
        before = list(Player.objects.order_by("pk").values_list("role", flat=True))
        self.assertCountEqual(before, TEMPLATES[5])
        self.assertEqual(self.post("start_game")["message"], "already_started")
        self.assertEqual(list(Player.objects.order_by("pk").values_list("role", flat=True)), before)
        self.assertEqual(self.post("set_avatar", avatar=AVATARS[1])["message"], "not_waiting")

    def test_mutations_reject_get(self):
        for path in ("create_or_join_room", "set_avatar", "start_game"):
            self.assertEqual(self.client.get(f"/{path}/").status_code, 405)

    def test_malformed_body_cannot_create_room(self):
        for body in ('[]', 'null', '{broken'):
            self.assertFalse(self.client.post('/create_or_join_room/', body, content_type='application/json').json()['ok'])
        self.assertEqual(Room.objects.count(), 0)
