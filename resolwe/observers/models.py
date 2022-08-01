"""The model Observer model."""
import uuid

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Count, Q

from .protocol import CHANGE_TYPE_CREATE, CHANGE_TYPE_DELETE, CHANGE_TYPE_UPDATE


def get_random_uuid():
    """Generate a random UUID in string format."""
    return uuid.uuid4().hex


class Observer(models.Model):
    """State of a model observer."""

    CHANGE_TYPES = (
        (CHANGE_TYPE_CREATE, "create"),
        (CHANGE_TYPE_UPDATE, "update"),
        (CHANGE_TYPE_DELETE, "delete"),
    )

    # Table of the observed resource
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    # Primary key of the observed resource (null if watching the whole table)
    object_id = models.PositiveIntegerField(null=True)
    # observed_resource = models.GenericForeignKey(null=True)

    change_type = models.CharField(choices=CHANGE_TYPES, max_length=6)

    @classmethod
    def get_interested(cls, content_type, object_id=None, change_type=None):
        """Find all observers watching for changes of a given item/table."""
        query = Q(content_type=content_type)
        if change_type is not None:
            query &= Q(change_type=change_type)
        query &= Q(object_id=object_id) | Q(object_id__isnull=True)
        return cls.objects.filter(query)

    def __str__(self):
        """Format the object representation."""
        return f"content_type={self.content_type} object_id={self.object_id} change={self.change_type}"

    class Meta:
        """Meta parameters for the Observer model."""

        unique_together = ("content_type", "object_id", "change_type")


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
    subscription_id = models.UUIDField(
        unique=True, default=get_random_uuid, editable=False
    )

    def subscribe(self, content_type, resource_ids, change_types):
        """Assign self to multiple observers at once."""
        for id in resource_ids:
            for change_type in change_types:
                observer, _ = Observer.objects.get_or_create(
                    content_type=content_type, object_id=id, change_type=change_type
                )
                self.observers.add(observer)

    def delete(self):
        """Clean up observers with no subscriptions before deleting self."""
        self.observers.annotate(subs=Count("subscriptions")).filter(subs=1).delete()
        super().delete()
