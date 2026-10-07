from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import CustomerProfile, User


@receiver(post_save, sender=User)
def ensure_profile(sender, instance: User, created: bool, **kwargs) -> None:
    if created:
        CustomerProfile.objects.get_or_create(user=instance)
