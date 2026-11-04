"""Settings for running the tests on this computer only: an in-memory SQLite database, so the tests never touch Supabase.
    python manage.py test --settings=config.settings_test"""
from .settings import *  # noqa: F401,F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]   # faster test users
