from django.urls import path

from . import views

urlpatterns = [
    path("products/", views.ProductListView.as_view(), name="product-list"),
    path("home/", views.HomeView.as_view(), name="home-sections"),
    path("products/suggest/", views.SuggestView.as_view(), name="product-suggest"),
    path("products/<slug:slug>/", views.ProductDetailView.as_view(), name="product-detail"),
    path("catalog/facets/", views.FacetsView.as_view(), name="catalog-facets"),
]
