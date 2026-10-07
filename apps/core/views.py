from django.core.cache import cache
from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Liveness for uptime monitors. Reports component status only, never config."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request) -> Response:
        checks = {}
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "error"
        try:
            cache.set("health", "1", 5)
            checks["cache"] = "ok" if cache.get("health") == "1" else "error"
        except Exception:
            checks["cache"] = "error"
        healthy = all(v == "ok" for v in checks.values())
        return Response({"status": "ok" if healthy else "degraded", "checks": checks}, status=200 if healthy else 503)
