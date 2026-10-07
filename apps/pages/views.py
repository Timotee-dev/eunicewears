"""Server-rendered page shells. All data and every action goes through /api/."""
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.sitemaps import Sitemap
from django.db.models import Avg, Count
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView

from apps.catalog.views import public_products
from apps.core import content as site_content
from apps.core.permissions import has_role
from apps.marketing.models import NewsletterSubscriber, Review


@method_decorator(ensure_csrf_cookie, name="dispatch")
class Page(TemplateView):
    pass


class GuestPage(Page):
    """Sign-in, register, etc. Signed-in customers go straight to their account."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("account")
        return super().dispatch(request, *args, **kwargs)


class MemberPage(LoginRequiredMixin, Page):
    pass


class ProductPage(Page):
    template_name = "shop/product.html"

    def get_context_data(self, **kwargs) -> dict:
        product = get_object_or_404(public_products(), slug=kwargs["slug"])
        url = f"{settings.SITE_URL}/product/{product.slug}/"
        variants = [v for v in product.variants.all() if v.is_active]
        prices = [v.unit_price for v in variants] or [product.current_price]
        images = [settings.SITE_URL + i.image.url if i.image.url.startswith("/") else i.image.url for i in product.images.all()]
        rating = Review.objects.filter(product=product, status=Review.Status.APPROVED).aggregate(avg=Avg("rating"), n=Count("id"))
        schema = {
            "@context": "https://schema.org", "@type": "Product", "name": product.name, "url": url,
            "description": product.short_description or product.description, "image": images,
            "brand": {"@type": "Brand", "name": settings.SITE_NAME}, "category": product.category.name,
            "offers": {
                "@type": "AggregateOffer", "priceCurrency": settings.DEFAULT_CURRENCY, "url": url,
                "lowPrice": f"{min(prices) / 100:.2f}", "highPrice": f"{max(prices) / 100:.2f}", "offerCount": max(len(variants), 1),
                "availability": "https://schema.org/InStock" if any(v.stock for v in variants) else "https://schema.org/OutOfStock",
            },
        }
        if rating["n"]:
            schema["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": round(rating["avg"], 1), "reviewCount": rating["n"]}
        crumbs = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Shop", "item": f"{settings.SITE_URL}/shop/"},
            {"@type": "ListItem", "position": 2, "name": product.name, "item": url}]}
        guide = site_content.get("size-guide")
        tables = [(label, site_content.table_rows(guide[key])) for key, label in (("oversized", "Oversized fit"), ("regular", "Regular fit")) if guide[key].strip()]
        return {**super().get_context_data(**kwargs), "product": product, "product_schema": schema, "crumb_schema": crumbs,
                "og_image": images[0] if images else "", "size_tables": tables,
                "size_columns": [c.strip() for c in guide["columns"].split(",") if c.strip()], "size_note": guide["note"]}


class HomePage(Page):
    template_name = "home.html"

    def get_context_data(self, **kwargs) -> dict:
        org = {"@context": "https://schema.org", "@type": "Organization", "name": settings.SITE_NAME, "url": settings.SITE_URL}
        return {**super().get_context_data(**kwargs), "org_schema": org,
                "headline_words": site_content.get("home")["headline"].split()}


class ContentPage(Page):
    template_name = "page.html"

    def get_context_data(self, **kwargs) -> dict:
        return {**super().get_context_data(**kwargs), "content": site_content.get(f"page-{self.kwargs['slug']}")}


def unsubscribe(request, token):
    subscriber = NewsletterSubscriber.objects.filter(token=token).first()
    if subscriber and subscriber.is_active:
        subscriber.is_active = False
        subscriber.save(update_fields=["is_active", "updated_at"])
    return render(request, "unsubscribed.html", {"found": subscriber is not None})


def robots(request):
    lines = ["User-agent: *", "Disallow: /api/", "Disallow: /dashboard/", "Disallow: /account/", "Disallow: /cart/",
             "Disallow: /checkout/", "Disallow: /wishlist/", f"Sitemap: {settings.SITE_URL}/sitemap.xml"]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


class ProductSitemap(Sitemap):
    changefreq, priority = "daily", 0.8

    def items(self):
        return public_products().order_by("id")

    def location(self, product) -> str:
        return f"/product/{product.slug}/"

    def lastmod(self, product):
        return product.updated_at


class StaticSitemap(Sitemap):
    changefreq, priority = "weekly", 0.5

    def items(self) -> list[str]:
        return ["/", "/shop/"] + [f"/{slug}/" for slug in site_content.PAGES]

    def location(self, path: str) -> str:
        return path


class SandboxPage(MemberPage):
    template_name = "shop/sandbox.html"

    def dispatch(self, request, *args, **kwargs):
        if not (settings.DEBUG and settings.PAYMENT_PROVIDER == "sandbox"):
            raise Http404()
        return super().dispatch(request, *args, **kwargs)


class DashboardPage(LoginRequiredMixin, Page):
    """Staff only. Customers get a 404, not a hint that the dashboard exists."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not has_role(request.user, "staff"):
            raise Http404()
        return super().dispatch(request, *args, **kwargs)


def not_found(request, exception=None):
    if request.path.startswith("/api/"):
        return JsonResponse({"error": {"code": "not_found", "message": "Not found.", "fields": None}}, status=404)
    return render(request, "404.html", status=404)


def server_error(request):
    if request.path.startswith("/api/"):
        return JsonResponse(
            {"error": {"code": "server_error", "message": "Something went wrong on our side.", "fields": None}}, status=500
        )
    return render(request, "500.html", status=500)
