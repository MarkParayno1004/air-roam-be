from django.core.management.base import BaseCommand, CommandError

from accounts.models import ROLE_ADMIN, ROLE_MARKETING, User


class Command(BaseCommand):
    help = "Create a staff user for the admin dashboard (use --admin for the first admin)."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--password", required=True)
        parser.add_argument("--admin", action="store_true")
        parser.add_argument("--marketing", action="store_true")

    def handle(self, *args, email, password, admin, marketing, **options):
        roles = [r for r, on in ((ROLE_ADMIN, admin), (ROLE_MARKETING, marketing)) if on]
        if not roles:
            raise CommandError("Give at least one of --admin / --marketing.")
        if User.all_objects.filter(email__iexact=email).exists():
            raise CommandError("A user with this email already exists.")
        User.objects.create_user(email, password, permissions=roles)
        self.stdout.write(self.style.SUCCESS(f"Created {email.lower()} with {roles}"))
