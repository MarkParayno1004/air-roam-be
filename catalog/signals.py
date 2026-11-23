from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from catalog import cache, rebuild
from catalog.models import Product, ProductVariant


def _catalog_changed():
    cache.invalidate()
    rebuild.trigger_rebuild()


@receiver([post_save, post_delete], sender=Product)
@receiver([post_save, post_delete], sender=ProductVariant)
def on_catalog_change(**kwargs):
    transaction.on_commit(_catalog_changed)
