from . import recorder


class AuditContextMiddleware:
    """Remembers the current request so a log row knows who (after DRF authenticates the JWT) and from which IP address."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = recorder.set_request(request)
        try:
            return self.get_response(request)
        finally:
            recorder.reset_request(token)
