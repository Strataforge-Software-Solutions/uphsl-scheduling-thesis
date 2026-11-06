from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .serializers import UserSerializer, ChangePasswordSerializer, BulkCreateUserSerializer

User = get_user_model()


def resolve_login_id(identifier):
    """Map what was typed to the account's real username (unchanged if there is no single match)."""
    import re
    from django.db.models import Q
    raw = (identifier or "").strip()
    m = re.match(r"(?i)^(?:UPHSM|UPHM)[\s_-]*(.+)$", raw)
    sid = (m.group(1) if m else raw).strip()
    qs = User.objects.filter(Q(username__iexact=raw) | Q(school_id__iexact=sid) | Q(username__iexact=f"UPHM-{sid}"))
    users = list(qs[:3])
    if len(users) == 1:
        return users[0].username
    exact = [u for u in users if u.username.lower() == raw.lower()]
    return exact[0].username if len(exact) == 1 else raw


class UPHSLTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login response also returns role/faculty_type/department so the
    frontend can route to the right dashboard view without guessing."""

    def validate(self, attrs):
        # People type their Login ID in several ways: UPHM-12345, just 12345, in lower case, or with a stray space
        # (the change-password screen even used to label it "UPHSM"). Find the ONE matching account first; the
        # password is then checked normally -- nothing about password validation is relaxed.
        attrs["username"] = resolve_login_id(attrs.get("username", ""))
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data


class LoginView(TokenObtainPairView):
    serializer_class = UPHSLTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            # audit log: who signed in, when, from which IP address (nothing about the password is stored)
            from audit import recorder
            u = User.objects.filter(pk=(response.data.get("user") or {}).get("id")).first()
            if u is not None:
                recorder.record("login", "user", u.pk, summary=f"{u.username} signed in", user=u, request=request)
        return response


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def me(request):
    """The signed-in user's CURRENT profile. The dashboard calls this on load so a change made on the
    server (e.g. a renamed department) shows up without having to sign out and in again."""
    return Response(UserSerializer(request.user).data)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def change_password(request):
    user = request.user
    serializer = ChangePasswordSerializer(data=request.data, context={"user": user})
    serializer.is_valid(raise_exception=True)

    # Forced first-login flow (default-password -> real password): skip the
    # old-password check entirely. The user is already JWT-authenticated
    # (they just logged in with the default password moments ago), so
    # re-verifying it added friction without adding real security -- this is
    # the straight-to-new-password screen the UI now shows for this case.
    # A future voluntary change (an already-onboarded user changing their
    # password by choice, not because must_change_password forced it) should
    # still require and verify old_password.
    if not user.must_change_password:
        old_password = serializer.validated_data.get("old_password", "")
        if not old_password or not user.check_password(old_password):
            return Response({"detail": "Old password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(serializer.validated_data["new_password"])
    user.must_change_password = False
    user.save()
    return Response({"detail": "Password updated."})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def bulk_create_users(request):
    if not request.user.is_it_admin:
        return Response({"detail": "Only the IT Admin can bulk-create accounts."}, status=status.HTTP_403_FORBIDDEN)
    rows = request.data.get("users", [])
    created, errors = [], []
    for row in rows:
        row = dict(row)
        # A Registrar / Dean / Faculty row without a School ID gets the next free one (R####, D####, F####, P####)
        auto = not str(row.get("school_id") or "").strip() and id_prefix_for(row.get("role"), row.get("faculty_type"))
        if auto:
            row["school_id"] = next_school_id(prefix=auto)
        serializer = BulkCreateUserSerializer(data=row)
        if not serializer.is_valid():
            errors.append({"row": row, "errors": serializer.errors})
            continue
        # BulkCreateUserSerializer is a plain Serializer, not a ModelSerializer,
        # so is_valid() never checks school_id/username uniqueness -- a
        # duplicate anywhere in the batch used to raise an uncaught
        # IntegrityError on .save() and 500 the ENTIRE request (losing every
        # row already created in this same loop iteration, with no response
        # ever reaching the Registrar). Each row now gets its own atomic
        # block so one bad row reports as a per-row error instead.
        try:
            for attempt in range(5 if auto else 1):
                try:
                    with transaction.atomic():
                        created.append(serializer.save().username)
                    break
                except IntegrityError:
                    if not auto or attempt == 4:
                        raise
                    serializer = BulkCreateUserSerializer(data={**row, "school_id": next_school_id(prefix=auto)})
                    serializer.is_valid(raise_exception=True)
        except IntegrityError:
            errors.append({
                "row": row,
                "errors": {"school_id": ["An account with this School ID (or the derived username) already exists."]},
            })
    return Response({"created": created, "errors": errors})


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def account_directory(request):
    """Registrar-only list of every account -- name, username, role,
    department, and whether they're still on their default (first-login)
    password -- feeding the People & Accounts "Account directory" table."""
    if not request.user.is_it_admin:
        return Response({"detail": "Only the IT Admin may view the account directory."}, status=status.HTTP_403_FORBIDDEN)

    rows = []
    for u in User.objects.order_by("role", "faculty_type", "last_name", "first_name"):
        rows.append({
            "id": u.id,
            "username": u.username,
            "full_name": u.get_full_name().strip() or u.username,
            "role": u.role,
            "faculty_type": u.faculty_type,
            "department": " & ".join(u.departments) or u.department,
            "must_change_password": u.must_change_password,
            "is_active": u.is_active,
            "extra_departments": u.extra_departments,
            "school_id": u.school_id,
            "email": u.email or "",
            "faculty_classification": {"full_time": "Full-time", "part_time": "Part-time"}.get(u.faculty_type, ""),
            "school_level": u.school_level or "",
        })
    return Response(rows)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def reset_password_to_default(request):
    """
    ONE clean way to handle a forgotten password: Registrar resets the account
    back to its default (password = school_id) and forces a change on next
    login -- same as day one. No email flow, no reset tokens, no separate
    'temporary password' concept to keep track of -- just one consistent
    state: must_change_password=True, password=school_id, always.
    """
    if not request.user.is_it_admin:
        return Response({"detail": "Only the IT Admin can reset a password."}, status=status.HTTP_403_FORBIDDEN)

    username = request.data.get("username", "").strip()
    if not username:
        return Response({"detail": "username is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return Response({"detail": f"No account found with username '{username}'."}, status=status.HTTP_404_NOT_FOUND)

    user.set_password(user.school_id)
    user.must_change_password = True
    user.save()
    return Response({"detail": f"Password for {user.username} reset to default (school ID). They'll be asked to change it on next login."})


FACULTY_ID_PREFIX = {"full_time": "F", "part_time": "P", "dean": "D"}


def id_prefix_for(role, faculty_type=None):
    """School ID letter for an account: R registrar, D dean, F full-time, P part-time (None = not generated)."""
    if role == "registrar":
        return "R"
    if role == "faculty":
        return FACULTY_ID_PREFIX.get(faculty_type)
    return None


def next_school_id(faculty_type=None, prefix=None):
    """Next free School ID: R#### / D#### / F#### / P####, continuing after the highest number already used
    (D1001 -> D1002 -> D1003 ...) and skipping anything taken, whatever its case."""
    import re
    prefix = prefix or FACULTY_ID_PREFIX[faculty_type]
    top = 1000
    for sid in User.objects.filter(school_id__startswith=prefix).values_list("school_id", flat=True):
        m = re.fullmatch(prefix + r"(\d+)", sid)
        if m:
            top = max(top, int(m.group(1)))
    n = top + 1
    while (User.objects.filter(school_id__iexact=f"{prefix}{n}").exists()
           or User.objects.filter(username__iexact=f"UPHM-{prefix}{n}").exists()):
        n += 1
    return f"{prefix}{n}"


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def dean_create_faculty(request):
    """A Dean creates a Full-time / Part-time faculty account for their own college. The School ID is
    generated here (never typed), is unique, and is returned so the Dean can hand it to the teacher.
    Default password = School ID; the teacher must change it on first login."""
    from django.core.exceptions import ValidationError as DjangoValidationError
    from django.core.validators import validate_email
    u = request.user
    if not (u.role == "faculty" and u.faculty_type == "dean"):
        return Response({"detail": "Only a Dean can create faculty accounts here."}, status=status.HTTP_403_FORBIDDEN)

    d = request.data
    first, last = str(d.get("first_name", "")).strip(), str(d.get("last_name", "")).strip()
    ftype = str(d.get("faculty_type", "")).strip()
    email = str(d.get("email", "")).strip()
    department = str(d.get("department", "") or "").strip() or (u.departments[0] if u.departments else "")
    errors = {}
    if not first:
        errors["first_name"] = "First name is required."
    if not last:
        errors["last_name"] = "Last name is required."
    if ftype not in FACULTY_ID_PREFIX:
        errors["faculty_type"] = "Choose Full-time or Part-time."
    if department not in u.departments:
        errors["department"] = "You can only add faculty to your own college."
    if email:
        try:
            validate_email(email)
        except DjangoValidationError:
            errors["email"] = "Enter a valid email address."
        else:
            if User.objects.filter(email__iexact=email).exists():
                errors["email"] = "That email address is already used by another account."
    specs = d.get("specializations") or []
    if isinstance(specs, str):
        specs = [x.strip() for x in specs.split(",")]
    if not isinstance(specs, list):
        errors["specializations"] = "Specializations must be a list."
    if errors:
        return Response({"detail": "; ".join(errors.values()), "errors": errors}, status=status.HTTP_400_BAD_REQUEST)

    from faculty.models import FacultyProfile
    from curriculum.models import AcademicField
    for _ in range(5):                              # a concurrent creation could take the same ID: retry
        sid = next_school_id(ftype)
        try:
            with transaction.atomic():
                user = User(school_id=sid, first_name=first, last_name=last, email=email, role="faculty",
                            faculty_type=ftype, department=department, must_change_password=True)
                user.set_password(sid)
                user.save()
                profile = FacultyProfile.objects.create(
                    user=user, degree=str(d.get("degree", "") or "").strip()[:255],
                    qualifications=str(d.get("qualifications", "") or "").strip()[:2000])
                fields = [AcademicField.objects.get_or_create(name=x.strip())[0] for x in specs if str(x).strip()]
                if fields:
                    profile.specializations.set(fields)
            break
        except IntegrityError:
            continue
    else:
        return Response({"detail": "Could not generate a unique School ID. Please try again."},
                        status=status.HTTP_409_CONFLICT)
    return Response({
        "id": user.id, "school_id": user.school_id, "username": user.username,
        "full_name": user.get_full_name(), "email": user.email, "department": user.department,
        "faculty_type": user.faculty_type,
        "faculty_classification": "Full-time" if ftype == "full_time" else "Part-time",
        "specializations": [f.name for f in profile.specializations.all()],
        "degree": profile.degree, "qualifications": profile.qualifications,
        "detail": f"Account created. School ID {user.school_id} (login {user.username}); default password is the School ID.",
    }, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def dean_parse_resume(request):
    """Dean uploads a resume (PDF / DOCX / TXT) -> suggested values for the Add Faculty form. Nothing is stored."""
    from curriculum.models import AcademicField
    from . import resume
    u = request.user
    if not (u.role == "faculty" and u.faculty_type == "dean"):
        return Response({"detail": "Only a Dean can read resumes here."}, status=status.HTTP_403_FORBIDDEN)
    f = request.FILES.get("file")
    if f is None:
        return Response({"detail": "Choose a resume file first."}, status=status.HTTP_400_BAD_REQUEST)
    if f.size > resume.MAX_BYTES:
        return Response({"detail": "That file is larger than 5 MB."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        text = resume.extract_text(f.name, f.read())
    except ValueError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        return Response({"detail": "That file could not be read. Try a text-based PDF or a Word file."},
                        status=status.HTTP_400_BAD_REQUEST)
    if len(text.strip()) < 20:
        return Response({"detail": "No readable text found (a scanned image?). Please fill in the form by hand."},
                        status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    data = resume.parse(text, list(AcademicField.objects.values_list("name", flat=True)))
    return Response(data)
