from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core import api_docs  # noqa: F401  (registers OpenAPI annotations)
from apps.core.views import HealthView

handler404 = "apps.pages.views.not_found"
handler500 = "apps.pages.views.server_error"

urlpatterns = [
    path(settings.DJANGO_ADMIN_PATH, admin.site.urls),
    path("api/health/", HealthView.as_view(), name="health"),
    path("api/auth/", include("apps.accounts.urls.auth")),
    path("api/account/", include("apps.accounts.urls.account")),
    path("api/admin/", include("apps.dashboard.urls")),
    path("api/", include("apps.catalog.urls")),
    path("api/", include("apps.marketing.urls")),
    path("api/", include("apps.cart.urls")),
    path("api/", include("apps.orders.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("", include("apps.pages.urls")),
]

if settings.DEBUG:
    urlpatterns = static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) + urlpatterns
