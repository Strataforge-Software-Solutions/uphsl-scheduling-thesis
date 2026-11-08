"""Local browser development using the database configured in backend/.env."""

from .settings import *  # noqa: F401,F403

# Port 3000 is occupied on this machine, so the React app runs on 3002.
CORS_ALLOWED_ORIGINS = [*CORS_ALLOWED_ORIGINS, "http://localhost:3002"]
