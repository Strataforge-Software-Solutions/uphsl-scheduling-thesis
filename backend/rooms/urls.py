from django.urls import path
from rest_framework.routers import DefaultRouter
from . import admin_views, dean_views
from .views import RoomViewSet

router = DefaultRouter()
router.register(r"", RoomViewSet, basename="room")

# Dean Dashboard -> Rooms tab (declared before the router so "dean/..." is not read as a room id)
urlpatterns = [
    path("dean/overview/", dean_views.overview, name="dean_room_overview"),
    path("admin/rooms/", admin_views.rooms, name="admin_rooms"),
    path("admin/rooms/<int:pk>/", admin_views.room_detail, name="admin_room_detail"),
    path("preview-choices/", dean_views.preview_choices, name="room_preview_choices"),
    path("dean/rooms/", dean_views.create_room, name="dean_room_create"),
    path("dean/rooms/<int:pk>/", dean_views.update_room, name="dean_room_update"),
    path("dean/subject-room/", dean_views.subject_room, name="dean_subject_room"),
    path("dean/enrollment/", dean_views.enrollment, name="dean_enrollment"),
    path("dean/department-building/", dean_views.department_building, name="dean_department_building"),
] + router.urls
