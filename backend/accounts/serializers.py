from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    departments = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()

    def get_departments(self, obj):
        return obj.departments

    def get_full_name(self, obj):
        return obj.get_full_name().strip() or obj.username

    def to_representation(self, obj):
        data = super().to_representation(obj)
        if obj.is_it_admin:
            data["role"] = "admin"          # a bare superuser gets the IT-admin dashboard
        return data

    class Meta:
        model = User
        fields = [
            "id", "username", "first_name", "last_name", "full_name",
            "role", "faculty_type", "department", "departments", "school_level", "must_change_password",
        ]


class ChangePasswordSerializer(serializers.Serializer):
    # Optional: the forced first-login flow (must_change_password=True) skips
    # asking for the current/default password at all -- the user just logged
    # in with it seconds ago and is already JWT-authenticated, so re-asking
    # for it added friction without adding real security. Kept optional here
    # (rather than removed) so a future voluntary "change my password" screen
    # for an already-onboarded user can still require and verify it.
    old_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    def validate_new_password(self, value):
        # Same Django validators as always (length, common / numeric-only, similarity to the account's own details).
        validate_password(value, user=self.context.get("user"))
        return value

    def validate(self, attrs):
        confirm = attrs.get("confirm_password")
        if confirm is not None and confirm != attrs["new_password"]:
            raise serializers.ValidationError({"confirm_password": ["The two passwords do not match."]})
        return attrs


class BulkCreateUserSerializer(serializers.Serializer):
    """
    One row of a Registrar/IT CSV import:
    school_id, first_name, last_name, role, faculty_type, department, specializations
    Username -> UPHM-<school_id>. Default password -> school_id (forces change on first login).
    """
    school_id = serializers.CharField()   # filled in by the view when left blank for Registrar / Dean / Faculty
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    role = serializers.ChoiceField(choices=User.ROLE_CHOICES)
    faculty_type = serializers.ChoiceField(choices=User.FACULTY_TYPE_CHOICES, required=False, allow_null=True)
    department = serializers.CharField(required=False, allow_blank=True)
    # Free-text degree/specialization names, e.g. ["BA in Filipino", "FCL"].
    # Only meaningful when role == "faculty" -- ignored otherwise.
    specializations = serializers.ListField(child=serializers.CharField(), required=False, default=list)

    def create(self, validated_data):
        user = User(
            school_id=validated_data["school_id"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            role=validated_data["role"],
            faculty_type=validated_data.get("faculty_type"),
            department=validated_data.get("department", ""),
            must_change_password=True,
        )
        user.set_password(validated_data["school_id"])  # default password = school ID
        user.save()

        # This endpoint used to create ONLY the User row -- any faculty
        # account added here (as opposed to via a seed script) never got a
        # FacultyProfile at all, so they'd be invisible to availability,
        # specialization, and scheduling features until someone noticed and
        # fixed it manually in Django admin. Every faculty account now
        # always gets a profile, with specializations attached if given.
        if user.role == "faculty":
            from faculty.models import FacultyProfile
            from curriculum.models import AcademicField

            profile = FacultyProfile.objects.create(user=user)
            specs = validated_data.get("specializations") or []
            if specs:
                fields = [AcademicField.objects.get_or_create(name=s.strip())[0] for s in specs if s.strip()]
                profile.specializations.set(fields)

        return user
