from django.contrib import admin

from .models import Player, Room, Vote


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("roomid", "status", "phase", "created_at")


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("roomid", "userid", "role", "userpsw")

    def roomid(self, obj):
        return obj.room.roomid


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ("roomid", "kind", "round_no", "agree", "disagree")

    def roomid(self, obj):
        return obj.room.roomid