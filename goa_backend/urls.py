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
    path("create_or_join_room/", views.create_or_join_room),
    path("set_avatar/", views.set_avatar),
    path("waiting_room/", views.waiting_room),
    path("start_game/", views.start_game),
    path("my_role/", views.my_role),
    path("room_state/", views.room_state),
    path("build_team/", views.build_team),
    path("vote/", views.vote),
    path("history/", views.history),
]
