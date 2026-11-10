"""JWT authentication rules for accounts that still need to set a real password."""
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class PasswordChangeRequiredJWTAuthentication(JWTAuthentication):
    """Do not rely on the frontend route guard to enforce first-login password changes."""

    ALLOWED_URL_NAMES = {"me", "change_password"}

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        match = getattr(request, "resolver_match", None)
        if user.must_change_password and getattr(match, "url_name", None) not in self.ALLOWED_URL_NAMES:
            raise AuthenticationFailed("Change your password before using the application.")
        return user, token
