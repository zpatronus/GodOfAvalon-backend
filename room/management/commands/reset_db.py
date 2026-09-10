import os
import shutil
from datetime import datetime

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connections


class Command(BaseCommand):
    help = (
        "Back up the current db.sqlite3, delete it, and rebuild an empty database "
        "with the current schema. Use after a deploy that changes the schema."
    )

    def handle(self, *args, **options):
        db_path = settings.DATABASES["default"]["NAME"]
        db_path = os.path.abspath(db_path)

        # 1. Back up the existing database (if any).
        if os.path.exists(db_path):
            backup_dir = os.path.join(os.path.dirname(db_path), "backups")
            os.makedirs(backup_dir, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_path = os.path.join(backup_dir, f"db.{stamp}.sqlite3")
            shutil.copy2(db_path, backup_path)
            self.stdout.write(self.style.SUCCESS(f"Backed up old database -> {backup_path}"))
        else:
            self.stdout.write(self.style.WARNING("No existing database to back up."))

        # 2. Close any open connections and drop the file so a fresh schema is rebuilt.
        connections.close_all()
        if os.path.exists(db_path):
            os.remove(db_path)
            self.stdout.write(self.style.SUCCESS("Removed old database."))

        # 3. Build the empty schema from the current migrations.
        call_command("migrate", interactive=False)
        self.stdout.write(self.style.SUCCESS("Created a fresh database with the current schema."))