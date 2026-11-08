"""Local development settings using an isolated SQLite database."""

from .settings import *  # noqa: F401,F403

# This override is applied after the normal settings (including any .env file),
# so local development never connects to the configured PostgreSQL database.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR.parent / "db.sqlite3",
    }
}

# React uses port 3002 here because port 3000 is already occupied locally.
CORS_ALLOWED_ORIGINS = [*CORS_ALLOWED_ORIGINS, "http://localhost:3002"]
