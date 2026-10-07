from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views, views_extra as extra

router = DefaultRouter()
router.register("products", views.ProductViewSet, basename="admin-product")
router.register("variants", views.VariantViewSet, basename="admin-variant")
router.register("categories", extra.CategoryViewSet, basename="admin-category")
router.register("shipping-methods", extra.ShippingMethodViewSet, basename="admin-shipping")
router.register("promo-codes", extra.PromoCodeViewSet, basename="admin-promo")
router.register("reviews", extra.ReviewViewSet, basename="admin-review")

urlpatterns = [
    path("stats/", views.StatsView.as_view()),
    path("analytics/", extra.AnalyticsView.as_view()),
    path("home-picks/", extra.HomePicksView.as_view()),
    path("home-picks/<int:pk>/", extra.HomePicksCategoryView.as_view()),
    path("customers/", extra.CustomerListView.as_view()),
    path("customers/<int:pk>/active/", extra.CustomerActiveView.as_view()),
    path("newsletter/", extra.NewsletterView.as_view()),
    path("newsletter/export/", extra.NewsletterExportView.as_view()),
    path("content/", extra.ContentView.as_view()),
    path("content/<slug:key>/", extra.ContentItemView.as_view()),
    path("images/<int:pk>/", views.ImageDeleteView.as_view()),
    path("orders/", views.OrderListView.as_view()),
    path("orders/<str:number>/", views.OrderDetailView.as_view()),
    path("orders/<str:number>/status/", views.OrderStatusView.as_view()),
] + router.urls
