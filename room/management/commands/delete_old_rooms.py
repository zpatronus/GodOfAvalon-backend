from django.core.management.base import BaseCommand
from room.models import Room
from datetime import datetime, timezone as dt_timezone


class Command(BaseCommand):
    help = "Delete rooms (and their players/votes via cascade) created before a given date"

    def add_arguments(self, parser):
        parser.add_argument("date", type=str, help="Date in the format YYYY-MM-DD")

    def handle(self, *args, **kwargs):
        date_str = kwargs["date"]
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=dt_timezone.utc)
        except ValueError:
            self.stdout.write(self.style.ERROR("Invalid date format. Use YYYY-MM-DD."))
            return

        rooms_to_delete = Room.objects.filter(created_at__lt=date)
        if not rooms_to_delete.exists():
            self.stdout.write(self.style.WARNING("No rooms found before the given date."))
            return

        count = rooms_to_delete.delete()[0]
        self.stdout.write(
            self.style.SUCCESS(f"Deleted {count} rows for rooms created before {date_str}.")
        )