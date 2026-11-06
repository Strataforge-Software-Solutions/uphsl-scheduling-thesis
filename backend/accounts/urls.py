from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views, admin_api, preferences

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("login/refresh/", TokenRefreshView.as_view(), name="login_refresh"),
    path("me/", views.me, name="me"),
    # "My settings": own profile + display preferences only (accounts/preferences.py)
    path("me/preferences/", preferences.my_preferences, name="my_preferences"),
    path("me/picture/", preferences.my_picture, name="my_picture"),
    path("me/picture/file/", preferences.my_picture_file, name="my_picture_file"),
    path("change-password/", views.change_password, name="change_password"),
    path("reset-password/", views.reset_password_to_default, name="reset_password_to_default"),
    path("bulk-create/", views.bulk_create_users, name="bulk_create_users"),
    path("dean/create-faculty/", views.dean_create_faculty, name="dean_create_faculty"),
    path("dean/parse-resume/", views.dean_parse_resume, name="dean_parse_resume"),
    path("directory/", views.account_directory, name="account_directory"),
    path("admin/overview/", admin_api.overview, name="admin_overview"),
    path("admin/clear-generated/", admin_api.clear_generated, name="admin_clear_generated"),
    path("admin/set-active/", admin_api.set_active, name="admin_set_active"),
    path("admin/set-dean-departments/", admin_api.set_dean_departments, name="admin_set_dean_departments"),
]
