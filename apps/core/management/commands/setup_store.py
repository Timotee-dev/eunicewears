"""Runs on every deploy: creates the owner account from OWNER_EMAIL / OWNER_PASSWORD (once) and the Tees category."""
import os

from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.catalog.models import Category


class Command(BaseCommand):
    help = "Create the owner account (from OWNER_EMAIL and OWNER_PASSWORD) and the first category."

    def handle(self, *args, **options):
        Category.objects.get_or_create(slug="tees", defaults={"name": "Tees"})
        email = os.environ.get("OWNER_EMAIL", "").strip().lower()
        password = os.environ.get("OWNER_PASSWORD", "")
        if not email or not password:
            self.stdout.write("OWNER_EMAIL / OWNER_PASSWORD not set: no owner account created.")
            return
        if User.objects.filter(email=email).exists():
            self.stdout.write("Owner account already exists: left unchanged.")
            return
        if len(password) < 10:
            self.stderr.write("OWNER_PASSWORD must be at least 10 characters: no owner account created.")
            return
        User.objects.create_superuser(email, password, first_name="Store", last_name="Owner")
        self.stdout.write(self.style.SUCCESS("Owner account created for " + email))
