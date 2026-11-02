import secrets

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Genera una clave secreta aleatoria para GPV_SECRET_KEY (cópiela en su archivo .env)."

    def handle(self, *args, **opts):
        self.stdout.write(secrets.token_urlsafe(50))
