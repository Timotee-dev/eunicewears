"""Runs on every deploy. Creates the owner account from OWNER_EMAIL / OWNER_PASSWORD (once) and the Tees category.
Safe to run again: it never changes an existing account's password and never creates products."""
import os

from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.catalog.models import Category


class Command(BaseCommand):
    help = "Create the owner account (from OWNER_EMAIL and OWNER_PASSWORD) and the first category."

    def handle(self, *args, **options) -> None:
        Category.objects.get_or_create(slug="tees", defaults={"name": "Tees"})
        from apps.orders.starter_rates import ensure_starter_rates

        added = ensure_starter_rates()
        if added:
            self.stdout.write(f"Added {added} starter delivery rates (placeholder fees: edit them in Dashboard > Settings).")
        email = os.environ.get("OWNER_EMAIL", "").strip().lower()
        password = os.environ.get("OWNER_PASSWORD", "")
        if not email or not password:
            self.stdout.write("OWNER_EMAIL / OWNER_PASSWORD not set: no owner account created.")
            return
        if User.objects.filter(email=email).exists():
            self.stdout.write(f"Owner account {email} already exists: left unchanged.")
            return
        if len(password) < 10:
            self.stderr.write("OWNER_PASSWORD must be at least 10 characters: no owner account created.")
            return
        User.objects.create_superuser(email, password, first_name=os.environ.get("OWNER_FIRST_NAME", "Store"),
                                      last_name=os.environ.get("OWNER_LAST_NAME", "Owner"))
        self.stdout.write(self.style.SUCCESS(f"Owner account created for {email}."))
