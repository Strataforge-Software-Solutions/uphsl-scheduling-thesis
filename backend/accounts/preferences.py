"""Personal settings ("My settings" page): profile details, a profile picture and display preferences.

Display only. Nothing here changes roles, permissions, scheduling rules or schedule data, and every
endpoint works on the signed-in user's own record only (there is no user id in any URL).

  GET   /api/accounts/me/preferences/      own profile + preferences (+ the allowed choices and defaults)
  PATCH /api/accounts/me/preferences/      change some of them; a value outside the allowed list -> 400
  POST  /api/accounts/me/picture/          upload / replace the picture (multipart field "picture")
  DELETE /api/accounts/me/picture/         remove it (the file is deleted)
  GET   /api/accounts/me/picture/file/     the picture itself (own picture only; the file name is never sent)
"""
import io
import os
import re
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import FileResponse, Http404
from rest_framework import permissions, serializers, status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from .models import UserPreference

User = get_user_model()

# ---------------------------------------------------------------- allowed values
THEMES = [("light", "Default"), ("royal", "Royal")]          # "light" is the stored value of the Default theme
TEXT_SIZES = [("small", "Small"), ("medium", "Medium"), ("large", "Large")]
DENSITIES = [("comfortable", "Comfortable"), ("compact", "Compact")]
MOTION = [("system", "Follow device"), ("on", "On"), ("off", "Off")]
TIME_FORMATS = [("12h", "12-hour (7:00 AM)"), ("24h", "24-hour (07:00)")]
DATE_FORMATS = [("mdy_short", "Nov 6, 2026"), ("dmy", "06/11/2026"), ("iso", "2026-11-06")]
WEEK_STARTS = [("mon", "Monday"), ("sun", "Sunday")]

PREF_FIELDS = ["theme", "text_size", "table_density", "reduce_motion", "time_format", "date_format", "week_start",
               "landing_page", "notify_schedule", "notify_conflict", "notify_exam", "notify_substitute"]
DEFAULTS = {f: UserPreference._meta.get_field(f).default for f in PREF_FIELDS}

# The pages (dashboard tabs) each role can already open: the same lists as the menus in the dashboards.
_REGISTRAR = [("home", "Home"), ("generate", "Generate Schedule"), ("minors", "Minor Schedules"), ("schedules", "Schedules"),
              ("exams", "Exam Schedule"), ("conflicts", "Conflicts"), ("curriculum", "Curriculum"),
              ("coverage", "Faculty Coverage"), ("analytics", "Analytics")]
_DEAN = [("home", "Home"), ("schedules", "Schedules"), ("exams", "Exam Schedule"), ("conflicts", "Conflicts"),
         ("curriculum", "Curriculum"), ("classlists", "Class Lists"), ("availability", "Faculty"),
         ("coverage", "Faculty Coverage"), ("analytics", "Analytics")]
_FACULTY = [("schedule", "My Schedule"), ("availability", "Availability")]
LANDING_PAGES = {
    "registrar": _REGISTRAR,
    "dean": _DEAN,
    "full_time": _FACULTY,
    "part_time": _FACULTY,
    "admin": [("overview", "Overview"), ("activity", "Activity"), ("audit", "Audit logs"), ("accounts", "Accounts"), ("rooms", "Rooms"), ("data", "Data Tools")],
    "principal": [("overview", "Home"), ("schedules", "Schedules"), ("analytics", "Analytics"), ("sections", "Sections"),
                  ("curriculum", "Curriculum"), ("faculty", "Faculty"), ("calendar", "Calendar"), ("settings", "Settings")],
    "teacher": [("schedule", "My Schedule"), ("profile", "My Profile")],
    "student": [("timetable", "My Timetable")],
}
ROLE_LABEL = {"registrar": "Registrar", "dean": "Dean", "full_time": "Full-time faculty", "part_time": "Part-time faculty",
              "admin": "IT Admin", "principal": "Principal", "teacher": "SHS/JHS Teacher", "student": "Student"}


def role_key(user):
    if user.is_it_admin:
        return "admin"
    if user.role == "faculty":
        return user.faculty_type or "full_time"
    return user.role


def landing_choices(user):
    return LANDING_PAGES.get(role_key(user), [])


def get_pref(user):
    """The user's row, created with the defaults the first time (existing users need no manual step)."""
    pref, _ = UserPreference.objects.get_or_create(user=user)
    return pref


# ---------------------------------------------------------------- serializers
PHONE_RE = re.compile(r"^\+?[0-9][0-9 ()\-]{5,24}$")
LOCKED = {"username": "Login ID", "school_id": "School ID", "role": "Role", "faculty_type": "Faculty type",
          "department": "Department", "departments": "Department", "school_level": "School level",
          # names come from the school's records: only the IT Admin / Registrar changes them
          "first_name": "Name", "last_name": "Name"}


class PreferencesSerializer(serializers.Serializer):
    # profile
    first_name = serializers.CharField(max_length=150, required=False, trim_whitespace=True,
                                       error_messages={"blank": "Enter your first name."})
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, trim_whitespace=True)
    email = serializers.EmailField(max_length=254, required=False, allow_blank=True,
                                   error_messages={"invalid": "Enter a valid email address, for example name@manila.uphsl.edu.ph."})
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, trim_whitespace=True)
    # display preferences
    theme = serializers.ChoiceField(choices=THEMES, required=False)
    text_size = serializers.ChoiceField(choices=TEXT_SIZES, required=False)
    table_density = serializers.ChoiceField(choices=DENSITIES, required=False)
    reduce_motion = serializers.ChoiceField(choices=MOTION, required=False)
    time_format = serializers.ChoiceField(choices=TIME_FORMATS, required=False)
    date_format = serializers.ChoiceField(choices=DATE_FORMATS, required=False)
    week_start = serializers.ChoiceField(choices=WEEK_STARTS, required=False)
    landing_page = serializers.CharField(max_length=30, required=False, allow_blank=True)
    notify_schedule = serializers.BooleanField(required=False)
    notify_conflict = serializers.BooleanField(required=False)
    notify_exam = serializers.BooleanField(required=False)
    notify_substitute = serializers.BooleanField(required=False)

    def validate_phone(self, value):
        if value and not PHONE_RE.match(value):
            raise serializers.ValidationError("Enter a phone number with digits only (it may start with + and contain spaces or dashes).")
        return value

    def validate_email(self, value):
        user = self.context["user"]
        if value and User.objects.filter(email__iexact=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("This email address is already used by another account.")
        return value

    def validate_landing_page(self, value):
        allowed = [k for k, _ in landing_choices(self.context["user"])]
        if value and value not in allowed:
            raise serializers.ValidationError("Your role cannot open that page. Pick one from the list.")
        return value


def _out(user, pref):
    allowed = landing_choices(user)
    landing = pref.landing_page if pref.landing_page in [k for k, _ in allowed] else ""   # a page the role lost -> normal home
    data = {f: getattr(pref, f) for f in PREF_FIELDS}
    data["landing_page"] = landing
    if data["theme"] not in dict(THEMES):
        data["theme"] = "light"                  # a theme that is no longer offered (Dark, Follow device) reads as Default
    return {
        "profile": {
            "first_name": user.first_name, "last_name": user.last_name, "email": user.email or "", "phone": pref.phone,
            "school_id": user.school_id, "username": user.username, "role": ROLE_LABEL.get(role_key(user), user.role),
            "department": " & ".join(user.departments) or (f"{user.school_level}" if user.school_level else ""),
            "has_picture": bool(pref.picture), "picture_version": int(pref.updated_at.timestamp()) if pref.picture else 0,
        },
        "preferences": data,
        "defaults": DEFAULTS,
        "choices": {
            "theme": THEMES, "text_size": TEXT_SIZES, "table_density": DENSITIES, "reduce_motion": MOTION,
            "time_format": TIME_FORMATS, "date_format": DATE_FORMATS, "week_start": WEEK_STARTS, "landing_page": allowed,
        },
    }


@api_view(["GET", "PATCH"])
@permission_classes([permissions.IsAuthenticated])
def my_preferences(request):
    user = request.user
    pref = get_pref(user)
    if request.method == "GET":
        return Response(_out(user, pref))

    locked = [label for key, label in LOCKED.items() if key in request.data]
    if locked:
        return Response({"detail": f"{', '.join(sorted(set(locked)))} cannot be changed here. Ask the IT Admin or the Registrar."},
                        status=status.HTTP_400_BAD_REQUEST)
    unknown = [k for k in request.data if k not in PreferencesSerializer().fields]
    if unknown:
        return Response({"detail": f"Unknown setting: {', '.join(sorted(unknown))}."}, status=status.HTTP_400_BAD_REQUEST)
    ser = PreferencesSerializer(data=request.data, context={"user": user}, partial=True)
    if not ser.is_valid():
        first = next(iter(ser.errors.items()))
        return Response({"detail": f"{first[1][0]}", "errors": ser.errors}, status=status.HTTP_400_BAD_REQUEST)
    v = ser.validated_data
    user_fields = [f for f in ("first_name", "last_name", "email") if f in v]
    for f in user_fields:
        setattr(user, f, v[f])
    if user_fields:
        user.save(update_fields=user_fields)
    for f in PREF_FIELDS + ["phone"]:
        if f in v:
            setattr(pref, f, v[f])
    pref.save()
    return Response(_out(user, pref))


# ---------------------------------------------------------------- profile picture
MAX_PICTURE_BYTES = 2 * 1024 * 1024
MAX_SIDE = 512
_FORMATS = {"JPEG": (".jpg", "image/jpeg"), "PNG": (".png", "image/png"), "WEBP": (".webp", "image/webp")}
_EXT_TYPE = {ext: ctype for ext, ctype in _FORMATS.values()}


class PictureError(Exception):
    pass


def picture_dir():
    path = os.path.join(settings.MEDIA_ROOT, "profile_pictures")
    os.makedirs(path, exist_ok=True)
    return path


def _picture_path(name):
    # names are always our own random hex + extension; anything else is refused (no path tricks)
    if not re.fullmatch(r"[0-9a-f]{32}\.(jpg|png|webp)", name or ""):
        return None
    return os.path.join(picture_dir(), name)


def clean_picture(upload):
    """Check the REAL content (not the name or the browser's type), shrink to 512 x 512 at most and drop
    every bit of metadata (EXIF, GPS, comments). Returns (bytes, extension)."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    if upload.size > MAX_PICTURE_BYTES:
        raise PictureError("The picture is larger than 2 MB. Choose a smaller file.")
    raw = upload.read(MAX_PICTURE_BYTES + 1)
    if len(raw) > MAX_PICTURE_BYTES:
        raise PictureError("The picture is larger than 2 MB. Choose a smaller file.")
    Image.MAX_IMAGE_PIXELS = 40_000_000          # refuses "decompression bomb" files
    try:
        probe = Image.open(io.BytesIO(raw))
        fmt = probe.format
        probe.verify()
        if fmt not in _FORMATS:
            raise PictureError("Use a JPG, PNG or WebP picture. Other types (such as GIF or SVG) are not accepted.")
        img = Image.open(io.BytesIO(raw))
        img.load()
    except PictureError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError):
        raise PictureError("This file is not a valid JPG, PNG or WebP picture.")

    img = ImageOps.exif_transpose(img)            # keep the photo upright before the orientation tag is dropped
    if getattr(img, "n_frames", 1) > 1:
        img.seek(0)
    keep_alpha = fmt in ("PNG", "WEBP") and ("A" in img.getbands() or "transparency" in img.info)
    img = img.convert("RGBA" if keep_alpha else "RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    clean = Image.frombytes(img.mode, img.size, img.tobytes())   # a fresh image: no EXIF, ICC, text chunks
    out = io.BytesIO()
    if fmt == "JPEG":
        clean.save(out, "JPEG", quality=88, optimize=True)
    elif fmt == "PNG":
        clean.save(out, "PNG", optimize=True)
    else:
        clean.save(out, "WEBP", quality=88)
    return out.getvalue(), _FORMATS[fmt][0]


def _remove_file(name):
    path = _picture_path(name)
    if path and os.path.exists(path):
        os.remove(path)


@api_view(["POST", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def my_picture(request):
    user = request.user
    pref = get_pref(user)
    if request.method == "DELETE":
        old = pref.picture
        pref.picture = ""
        pref.save(update_fields=["picture", "updated_at"])
        _remove_file(old)
        return Response(_out(user, pref))

    upload = request.FILES.get("picture")
    if upload is None:
        return Response({"detail": "Choose a picture to upload."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        data, ext = clean_picture(upload)
    except PictureError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    name = secrets.token_hex(16) + ext            # random name: the uploaded file name is never used
    tmp = os.path.join(picture_dir(), name + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, os.path.join(picture_dir(), name))
    old = pref.picture
    pref.picture = name
    pref.save(update_fields=["picture", "updated_at"])
    if old and old != name:
        _remove_file(old)
    return Response(_out(user, pref), status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def my_picture_file(request):
    pref = UserPreference.objects.filter(user=request.user).first()
    path = _picture_path(pref.picture) if pref else None
    if not path or not os.path.exists(path):
        raise Http404("No picture.")
    resp = FileResponse(open(path, "rb"), content_type=_EXT_TYPE[os.path.splitext(path)[1]])
    resp["Cache-Control"] = "private, max-age=0, must-revalidate"
    resp["X-Content-Type-Options"] = "nosniff"
    return resp
