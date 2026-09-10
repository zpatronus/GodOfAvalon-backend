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