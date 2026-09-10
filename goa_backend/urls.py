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
from django.urls import path

from room import views

urlpatterns = [
    path("admin/", admin.site.urls),
    # credential-free read
    path("room_status/<str:roomid>/", views.room_status),
    # every authed/mutating call goes through POST with a JSON body (no creds in URL)
    path("csrf/", views.get_csrf_token),
    path("create_room/", views.create_room),
    path("join_room/", views.join_room),
    path("waiting_room/", views.waiting_room),
    path("start_game/", views.start_game),
    path("my_role/", views.my_role),
    path("room_state/", views.room_state),
    path("build_team/", views.build_team),
    path("vote/", views.vote),
    path("history/", views.history),
]