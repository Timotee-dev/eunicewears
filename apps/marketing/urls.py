from django.urls import path

from . import views

urlpatterns = [
    path("wishlist/", views.WishlistView.as_view(), name="wishlist"),
    path("wishlist/<int:product_id>/", views.WishlistItemView.as_view(), name="wishlist-item"),
    path("products/<slug:slug>/reviews/", views.ProductReviewsView.as_view(), name="product-reviews"),
    path("newsletter/", views.NewsletterView.as_view(), name="newsletter"),
    path("back-in-stock/", views.BackInStockView.as_view(), name="back-in-stock"),
]
