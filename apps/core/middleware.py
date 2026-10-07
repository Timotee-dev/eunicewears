from django.conf import settings

CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https:; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        path = request.path
        # Swagger UI and Django admin ship inline assets; keep the strict policy for everything else.
        if not (path.startswith("/api/docs") or path.startswith("/" + settings.DJANGO_ADMIN_PATH)):
            response.setdefault("Content-Security-Policy", CSP)
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response
