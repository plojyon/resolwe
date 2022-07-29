"""The model Observer model."""
import random

from django.conf import settings
from django.db import models
from django.db.models import Count, Q

from .protocol import CHANGE_TYPE_CREATE, CHANGE_TYPE_DELETE, CHANGE_TYPE_UPDATE


def get_random_hash():
    """Generate a random 256-bit number as a hex string."""
    return hex(random.randint(0, 2**128))[2:]


class Observer(models.Model):
    """State of a model observer."""

    CHANGE_TYPES = (
        (CHANGE_TYPE_CREATE, "create"),
        (CHANGE_TYPE_UPDATE, "update"),
        (CHANGE_TYPE_DELETE, "delete"),
    )

    # Table of the observed resource
    table = models.CharField(max_length=100)
    # Primary key of the observed resource (null if watching the whole table)
    resource_pk = models.IntegerField(null=True)
    change_type = models.CharField(choices=CHANGE_TYPES, max_length=6)

    @classmethod
    def get_interested(cls, table, resource_pk=None, change_type=None):
        """Find all observers watching for changes of a given item/table."""
        query = Q(table=table)
        if change_type is not None:
            query &= Q(change_type=change_type)
        query &= Q(resource_pk=resource_pk) | Q(resource_pk__isnull=True)
        return cls.objects.filter(query)

    def __str__(self):
        """Format the object representation."""
        return f"table={self.table} resource_pk={self.resource_pk} change={self.change_type}"

    class Meta:
        """Meta parameters for the Observer model."""

        unique_together = ("table", "resource_pk", "change_type")


class Subscription(models.Model):
    """Subscription to several observers."""

    observers = models.ManyToManyField("Observer", related_name="subscriptions")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    created = models.DateTimeField(auto_now_add=True)

    # ID of the websocket session (can have multiple observers)
    session_id = models.CharField(max_length=100)
    # Unique ID for the client to remember which subscription a signal belongs to
    subscription_id = models.CharField(
        max_length=32, unique=True, default=get_random_hash
    )

    def subscribe(self, table, resource_ids, change_types):
        """Assign self to multiple observers at once."""
        for id in resource_ids:
            for change_type in change_types:
                observer, _ = Observer.objects.get_or_create(
                    table=table, resource_pk=id, change_type=change_type
                )
                self.observers.add(observer)

    def delete(self):
        """Clean up observers with no subscriptions before deleting self."""
        for observer in self.observers.annotate(subs=Count("subscriptions")).filter(
            subs=1
        ):
            observer.delete()
        super().delete()
