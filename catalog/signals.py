from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from catalog import cache, rebuild
from catalog.models import Product, Region, RegionPlan


def _catalog_changed():
    cache.invalidate()
    rebuild.trigger_rebuild()


@receiver([post_save, post_delete], sender=Product)
@receiver([post_save, post_delete], sender=Region)
@receiver([post_save, post_delete], sender=RegionPlan)
def on_catalog_change(**kwargs):
    transaction.on_commit(_catalog_changed)
