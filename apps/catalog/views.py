from django.db.models import Exists, OuterRef, Q
from django.db.models.functions import Coalesce
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import HOME_PICKS_PER_CATEGORY, Category, HomePick, Product, ProductVariant
from .serializers import CategorySerializer, ProductDetailSerializer, ProductListSerializer


def public_products():
    return (
        Product.objects.filter(is_published=True, archived_at__isnull=True, category__is_active=True)
        .select_related("category")
        .prefetch_related("images", "variants")  # no N+1 on lists
    )


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except ValueError:
        return None


class ProductListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductListSerializer

    def get_queryset(self):
        p = self.request.query_params
        qs = public_products().annotate(sort_price=Coalesce("discount_price", "price"))
        variants = ProductVariant.objects.filter(product=OuterRef("pk"), is_active=True)
        for param in ("fit", "size", "color"):
            if p.get(param):
                variants = variants.filter(**{f"{param}__iexact": p[param]})
        if p.get("in_stock") == "1":
            variants = variants.filter(stock__gt=0)
        if any(p.get(k) for k in ("fit", "size", "color")) or p.get("in_stock") == "1":
            qs = qs.filter(Exists(variants))
        if p.get("category"):
            qs = qs.filter(Q(category__slug=p["category"]) | Q(category__parent__slug=p["category"]))
        if p.get("collection"):
            qs = qs.filter(collections__slug=p["collection"])
        flag = {"new": "is_new_arrival", "best": "is_best_seller", "featured": "is_featured"}.get(p.get("flag", ""))
        if flag:
            qs = qs.filter(**{flag: True})
        if (low := _int(p.get("min_price"))) is not None:
            qs = qs.filter(sort_price__gte=low)
        if (high := _int(p.get("max_price"))) is not None:
            qs = qs.filter(sort_price__lte=high)
        if q := p.get("q", "").strip()[:80]:
            qs = qs.filter(
                Q(name__icontains=q) | Q(description__icontains=q) | Q(category__name__icontains=q)
                | Exists(ProductVariant.objects.filter(product=OuterRef("pk")).filter(Q(sku__iexact=q) | Q(color__icontains=q)))
            )
        order = {"price_asc": "sort_price", "price_desc": "-sort_price"}.get(p.get("sort", ""), "-created_at")
        return qs.order_by(order, "-id").distinct()


class ProductDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductDetailSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return public_products()


class FacetsView(APIView):
    """What the shop's filter panel can offer, taken from real, purchasable variants."""

    permission_classes = [AllowAny]

    def get(self, request) -> Response:
        variants = ProductVariant.objects.filter(is_active=True, product__in=public_products().values("pk"))
        return Response({
            "categories": CategorySerializer(Category.objects.filter(is_active=True), many=True).data,
            "fits": sorted({f for f in variants.values_list("fit", flat=True) if f}),
            "sizes": list(dict.fromkeys(variants.order_by("id").values_list("size", flat=True))),
            "colors": sorted(set(variants.values_list("color", flat=True))),
        })


class SuggestView(APIView):
    """Type-ahead for the header search: a handful of matching products."""

    permission_classes = [AllowAny]

    def get(self, request) -> Response:
        q = request.query_params.get("q", "").strip()[:60]
        if len(q) < 2:
            return Response([])
        matches = public_products().filter(
            Q(name__icontains=q) | Q(category__name__icontains=q)
            | Exists(ProductVariant.objects.filter(product=OuterRef("pk")).filter(Q(color__icontains=q) | Q(sku__iexact=q)))
        )[:6]
        return Response([{"name": p.name, "slug": p.slug, "price": p.current_price} for p in matches])


def home_sections() -> list[dict]:
    """Home page shelves: per category, the owner's picks in their order. A category with no picks yet
    shows its newest products so the page is never empty while the owner is still choosing."""
    sections = []
    for category in Category.objects.filter(is_active=True):
        products = public_products().filter(category=category)
        picked_ids = list(HomePick.objects.filter(category=category, product__in=products).values_list("product_id", flat=True))
        if picked_ids:
            by_id = {p.pk: p for p in products.filter(pk__in=picked_ids)}
            chosen = [by_id[pk] for pk in picked_ids if pk in by_id][:HOME_PICKS_PER_CATEGORY]
        else:
            chosen = list(products.order_by("-created_at")[:HOME_PICKS_PER_CATEGORY])
        if chosen:
            sections.append({"category": category, "products": chosen, "picked": bool(picked_ids)})
    return sections


class HomeView(APIView):
    permission_classes = [AllowAny]

    def get(self, request) -> Response:
        return Response([
            {"category": {"name": s["category"].name, "slug": s["category"].slug},
             "products": ProductListSerializer(s["products"], many=True, context={"request": request}).data}
            for s in home_sections()
        ])
