"""
UPHSL Scheduling System — Django settings skeleton.
Fill in SECRET_KEY, DB credentials, and ALLOWED_HOSTS before deploying.
"""
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "change-me-before-deploy"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",

    # Project apps — one per architecture module
    "accounts",       # Users, roles, faculty_type, auth
    "curriculum",     # Subject, Program, prerequisites
    "faculty",        # Teacher profile, availability, workload
    "rooms",          # Room, capacity, type
    "engine",         # Section, Schedule, Constraint, Scheduling Engine
    "exams",          # ExamSchedule — Registrar owns minors, Dean owns majors, shared conflict layer
    "analytics",      # room utilization, workload distribution, efficiency
    "notifications",  # schedule updates, conflict alerts, Log
    "basic_ed",       # Senior High / Junior High scheduling -- separate from the college tables
    "audit",          # audit logs: who changed what, when, before / after, from which IP (append-only)
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "audit.middleware.AuditContextMiddleware",       # who / which IP for the audit logs
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

import os
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env", override=True)   # the .env file wins over stale DB_* variables left in the terminal / Windows
except ImportError:   # python-dotenv not installed in this Python: run  pip install -r requirements.txt
    import sys
    print("WARNING: python-dotenv is not installed, so the .env file (database settings) was NOT read. "
          "Run:  pip install -r requirements.txt", file=sys.stderr)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "postgres"),
        "USER": os.environ.get("DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", ""),   # Supabase: Project Settings > Database > Connection string (Host)
        "PORT": os.environ.get("DB_PORT", "5432"),
        # fail with a clear error after 15 s instead of hanging when the database is unreachable/paused
        # keepalives stop wifi / the Supabase pooler from silently dropping a long-running command
        "OPTIONS": {"connect_timeout": 15, "keepalives": 1, "keepalives_idle": 30,
                    "keepalives_interval": 10, "keepalives_count": 5},
    }
}
# --- Using local MySQL instead of Supabase? Comment out the block above and use this: ---
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.mysql",
#         "NAME": os.environ.get("DB_NAME", "uphsl_scheduling"),
#         "USER": os.environ.get("DB_USER", "root"),
#         "PASSWORD": os.environ.get("DB_PASSWORD", ""),
#         "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
#         "PORT": os.environ.get("DB_PORT", "3306"),
#         "OPTIONS": {"charset": "utf8mb4"},
#     }
# }
# For local dev without any server handy, swap back to:
# DATABASES["default"] = {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=8),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
]
# If testing from another device on the same Wi-Fi (phone, another PC), add your
# machine's actual LAN IP here too, e.g. "http://192.168.100.9:3000" -- and set
# REACT_APP_API_BASE_URL in frontend/.env to match (see services/api.js comment).
# CORS_ALLOWED_ORIGINS.append("http://192.168.100.9:3000")

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Manila"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

# Uploaded files (profile pictures only). Not published under a public URL: a picture is sent only to its owner
# through /api/accounts/me/picture/file/. Back this folder up together with the database.
MEDIA_ROOT = os.environ.get("MEDIA_ROOT", str(BASE_DIR / "media"))
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
