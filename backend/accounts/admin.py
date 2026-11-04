from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


class UFastUserAdmin(UserAdmin):
    # school ID / role / department details were editable before only through custom fields
    fieldsets = UserAdmin.fieldsets + (
        ("U-FAST", {"fields": ("school_id", "role", "faculty_type", "department", "extra_departments",
                               "must_change_password")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("U-FAST", {"fields": ("school_id", "role", "faculty_type", "department", "extra_departments")}),
    )
    list_display = ("username", "get_full_name", "role", "faculty_type", "department", "extra_departments")


admin.site.register(User, UFastUserAdmin)
