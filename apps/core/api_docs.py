"""OpenAPI annotations for the hand-written API views, kept in one place so the views stay readable.
Imported once from config/urls.py. Browse the result at /api/docs/."""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view

from apps.accounts import views as accounts
from apps.accounts.serializers import PasswordChangeSerializer, UserSerializer
from apps.cart import views as cart
from apps.catalog import views as catalog
from apps.core import views as core
from apps.dashboard import views as dash
from apps.dashboard import views_extra as extra
from apps.dashboard.serializers import AdminOrderDetailSerializer
from apps.marketing.serializers import MessageSerializer
from apps.orders import views as orders
from apps.orders.serializers import CheckoutSerializer

OBJ = OpenApiTypes.OBJECT


def doc(view, tag: str, **methods) -> None:
    extend_schema_view(**{m: extend_schema(tags=[tag], **kwargs) for m, kwargs in methods.items()})(view)


doc(core.HealthView, "System", get=dict(responses=OBJ, summary="Liveness and dependency checks"))
doc(accounts.CsrfView, "Authentication", get=dict(responses=OBJ, summary="Issue a CSRF token"))
doc(accounts.LogoutView, "Authentication", post=dict(request=None, responses={204: None}))
doc(accounts.MeView, "Authentication", get=dict(responses=UserSerializer), patch=dict(request=UserSerializer, responses=UserSerializer))
doc(accounts.PasswordChangeView, "Authentication", post=dict(request=PasswordChangeSerializer, responses=MessageSerializer))

CART = dict(responses=OBJ, description="Returns the full cart: lines, count and server-computed subtotal in kobo.")
doc(cart.CartView, "Cart", get=CART)
doc(cart.CartItemsView, "Cart", post=dict(request=cart.AddSerializer, **CART))
doc(cart.CartItemView, "Cart", patch=dict(request=cart.QuantitySerializer, **CART), delete=dict(**CART))

doc(catalog.FacetsView, "Products", get=dict(responses=OBJ, summary="Filter options available in the shop"))
doc(catalog.SuggestView, "Products", get=dict(responses=OBJ, summary="Search suggestions (send ?q=)"))

doc(orders.QuoteView, "Checkout", post=dict(request=CheckoutSerializer, responses=OBJ, summary="Totals for the cart, address and promo code"))
doc(orders.CheckoutView, "Checkout", post=dict(request=CheckoutSerializer, responses=OBJ, summary="Place the order, reserve stock, start payment"))
doc(orders.VerifyPaymentView, "Payments", post=dict(request=orders.ReferenceSerializer, responses=OBJ,
                                                   summary="Ask the gateway whether this payment succeeded"))
doc(orders.SandboxOutcomeView, "Payments", post=dict(request=OBJ, responses=OBJ, summary="Development only: approve or decline a test payment"))

doc(dash.StatsView, "Admin", get=dict(responses=OBJ, summary="Overview figures"))
doc(dash.OrderDetailView, "Admin", get=dict(responses=AdminOrderDetailSerializer), patch=dict(request=OBJ, responses=AdminOrderDetailSerializer))
doc(dash.OrderStatusView, "Admin", post=dict(request=dash.OrderStatusSerializer, responses=AdminOrderDetailSerializer,
                                            summary="Move an order to its next status (refunds automatically when needed)"))
doc(extra.AnalyticsView, "Admin", get=dict(responses=OBJ, summary="Sales for a date range (?from=YYYY-MM-DD&to=YYYY-MM-DD)"))
doc(extra.NewsletterView, "Admin", get=dict(responses=OBJ))
doc(extra.ContentView, "Admin", get=dict(responses=OBJ, summary="Editable content blocks and their fields"))
doc(extra.ContentItemView, "Admin", put=dict(request=OBJ, responses=OBJ))
doc(catalog.HomeView, "Products", get=dict(responses=OBJ, summary="Home page shelves: up to ten owner-chosen products per category"))
doc(extra.HomePicksView, "Admin", get=dict(responses=OBJ, summary="Home page picks and the products available to choose from"))
doc(extra.HomePicksCategoryView, "Admin", put=dict(request=extra.HomePicksSerializer, responses=OBJ, summary="Replace one category's home page picks (max 10)"))
