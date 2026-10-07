from django.urls import path

from . import views

urlpatterns = [
    path("checkout/quote/", views.QuoteView.as_view(), name="checkout-quote"),
    path("checkout/", views.CheckoutView.as_view(), name="checkout"),
    path("payments/verify/", views.VerifyPaymentView.as_view(), name="payment-verify"),
    path("payments/webhook/", views.webhook, name="payment-webhook"),
    path("payments/sandbox/<str:reference>/", views.SandboxOutcomeView.as_view(), name="payment-sandbox"),
    path("orders/", views.OrderListView.as_view(), name="order-list"),
    path("orders/<str:number>/", views.OrderDetailView.as_view(), name="order-detail"),
]
