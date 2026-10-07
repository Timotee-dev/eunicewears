from django.core.management.base import BaseCommand

from apps.orders.services import expire_unpaid


class Command(BaseCommand):
    help = "Cancel orders left unpaid and return their stock. Run every 15 minutes from cron."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--minutes", type=int, default=60)

    def handle(self, *args, **options) -> None:
        self.stdout.write(f"Cancelled {expire_unpaid(options['minutes'])} unpaid order(s).")
