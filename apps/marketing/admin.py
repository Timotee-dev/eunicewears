from django.contrib import admin

from .models import BackInStockRequest, NewsletterSubscriber, PromoCode, Review

admin.site.register([PromoCode, Review, NewsletterSubscriber, BackInStockRequest])
