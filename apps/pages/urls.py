from django.contrib.sitemaps.views import sitemap
from django.urls import path, re_path

from .views import (ContentPage, DashboardPage, GuestPage, HomePage, MemberPage, Page, ProductPage, ProductSitemap,
                    SandboxPage, StaticSitemap, robots, unsubscribe)


def dash(template: str):
    return DashboardPage.as_view(template_name=f"dashboard/{template}.html")


urlpatterns = [
    path("", HomePage.as_view(), name="home"),
    path("robots.txt", robots, name="robots"),
    path("sitemap.xml", sitemap, {"sitemaps": {"pages": StaticSitemap, "products": ProductSitemap}}, name="sitemap"),
    re_path(r"^(?P<slug>about|faq|shipping|returns|privacy|terms)/$", ContentPage.as_view(), name="content-page"),
    path("newsletter/unsubscribe/<uuid:token>/", unsubscribe, name="unsubscribe"),
    path("wishlist/", MemberPage.as_view(template_name="shop/wishlist.html"), name="wishlist"),
    path("shop/", Page.as_view(template_name="shop/shop.html"), name="shop"),
    path("product/<slug:slug>/", ProductPage.as_view(), name="product"),
    path("cart/", Page.as_view(template_name="shop/cart.html"), name="cart"),
    path("checkout/", MemberPage.as_view(template_name="shop/checkout.html"), name="checkout"),
    path("order-success/", MemberPage.as_view(template_name="shop/success.html"), name="order-success"),
    path("payments/sandbox/<str:reference>/", SandboxPage.as_view(), name="sandbox-pay"),
    path("account/", MemberPage.as_view(template_name="account/index.html"), name="account"),
    path("account/orders/<str:number>/", MemberPage.as_view(template_name="account/order.html"), name="account-order"),
    path("account/login/", GuestPage.as_view(template_name="auth/login.html"), name="login"),
    path("account/register/", GuestPage.as_view(template_name="auth/register.html"), name="register"),
    path("account/verify-email/", Page.as_view(template_name="auth/verify.html"), name="verify-email"),
    path("account/forgot-password/", GuestPage.as_view(template_name="auth/forgot.html"), name="forgot-password"),
    path("account/reset-password/", Page.as_view(template_name="auth/reset.html"), name="reset-password"),
    path("dashboard/", dash("overview"), name="dashboard"),
    path("dashboard/orders/", dash("orders"), name="dashboard-orders"),
    path("dashboard/orders/<str:number>/", dash("order"), name="dashboard-order"),
    path("dashboard/analytics/", dash("analytics"), name="dashboard-analytics"),
    path("dashboard/customers/", dash("customers"), name="dashboard-customers"),
    path("dashboard/reviews/", dash("reviews"), name="dashboard-reviews"),
    path("dashboard/marketing/", dash("marketing"), name="dashboard-marketing"),
    path("dashboard/content/", dash("content"), name="dashboard-content"),
    path("dashboard/home/", dash("home"), name="dashboard-home"),
    path("dashboard/settings/", dash("settings"), name="dashboard-settings"),
    path("dashboard/products/", dash("products"), name="dashboard-products"),
    path("dashboard/products/new/", dash("product"), name="dashboard-product-new"),
    path("dashboard/products/<int:pk>/", dash("product"), name="dashboard-product"),
]
