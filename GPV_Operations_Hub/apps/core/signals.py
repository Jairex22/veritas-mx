from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile, Role


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile(sender, instance, created, raw=False, **kwargs):
    if raw:  # loaddata / restore: the profile comes from the fixture
        return
    if created:
        Profile.objects.get_or_create(
            user=instance,
            defaults={"role": Role.ADMIN if instance.is_superuser else Role.OPERATOR, "all_areas": instance.is_superuser},
        )
