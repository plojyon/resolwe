"""The model Observer model."""
import uuid

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.db.models import Count, Q

from .protocol import (
    CHANGE_TYPE_CREATE,
    CHANGE_TYPE_DELETE,
    CHANGE_TYPE_UPDATE,
    GROUP_SESSIONS,
    TYPE_ITEM_UPDATE,
)


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

    # Table of the observed resource.
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    # Primary key of the observed resource (null if watching the whole table).
    object_id = models.PositiveIntegerField(null=True)

    change_type = models.CharField(choices=CHANGE_TYPES, max_length=6)

    class Meta:
        """Meta parameters for the Observer model."""

        unique_together = ("content_type", "object_id", "change_type")
        indexes = [
            models.Index(name="idx_observer_object_id", fields=["object_id"]),
        ]

    @classmethod
    def get_interested(cls, content_type, object_id=None, change_type=None):
        """Find all observers watching for changes of a given item/table."""
        query = Q(content_type=content_type)
        if change_type is not None:
            query &= Q(change_type=change_type)
        query &= Q(object_id=object_id) | Q(object_id__isnull=True)
        return cls.objects.filter(query)

    @classmethod
    def observe_instance_changes(cls, instance, change_type):
        """Handle a notification about an instance change."""

        observers = Observer.get_interested(
            change_type=change_type,
            content_type=ContentType.objects.get_for_model(type(instance)),
            object_id=instance.pk,
        )

        # Forward the message to the appropriate groups.
        for subscriber in Subscription.objects.filter(observers__in=observers):
            has_permission = (
                type(instance)
                .objects.filter(pk=instance.pk)
                .filter_for_user(user=subscriber.user)
                .exists()
            )
            if not has_permission:
                continue

            # Register on_commit callbacks to send the signals.
            Subscription.notify(subscriber.session_id, instance, change_type)

    @classmethod
    def observe_permission_changes(cls, instance, gains, losses):
        """Handle a notification about a permission change.

        Given an instance and a set of user_ids who gained/lost permissions for it,
        only relevant observers will be notified of the instance's creation/deletion.
        """
        for change_type, user_ids in (
            (CHANGE_TYPE_CREATE, gains),
            (CHANGE_TYPE_DELETE, losses),
        ):
            # A shortcut if nothing actually changed.
            if len(user_ids) == 0:
                continue

            # Find all sessions who have observers registered on this object.
            interested = Observer.get_interested(
                change_type=change_type,
                content_type=ContentType.objects.get_for_model(type(instance)),
                object_id=instance.pk,
            )
            # Of all interested users, select only those whose permissions changed.
            session_ids = set(
                Subscription.objects.filter(observers__in=interested)
                .filter(user__in=user_ids)
                .values_list("session_id", flat=True)
                .distinct()
            )

            for session_id in session_ids:
                Subscription.notify(session_id, instance, change_type)

    def __str__(self):
        """Format the object representation."""
        return f"content_type={self.content_type} object_id={self.object_id} change={self.change_type}"


class Subscription(models.Model):
    """Subscription to several observers."""

    observers = models.ManyToManyField("Observer", related_name="subscriptions")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    created = models.DateTimeField(auto_now_add=True)

    # ID of the websocket session (can have multiple observers).
    session_id = models.CharField(max_length=100)
    # Unique ID for the client to remember which subscription a signal belongs to.
    subscription_id = models.UUIDField(
        unique=True, default=get_random_uuid, editable=False
    )

    class Meta:
        """Meta parameters for the Subscription model."""

        indexes = [
            models.Index(name="idx_subscription_session_id", fields=["session_id"]),
        ]

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

    @classmethod
    def notify(cls, session_id, instance, change_type):
        """Register a callback to send a change notification on transaction commit."""
        notification = {
            "type": TYPE_ITEM_UPDATE,
            "content_type_pk": ContentType.objects.get_for_model(type(instance)).pk,
            "change_type": change_type,
            "object_id": str(instance.pk),
        }

        # Define a callback, but copy variable values.
        def trigger(
            channel_layer=get_channel_layer(),
            channel=GROUP_SESSIONS.format(session_id=session_id),
            notification=notification,
        ):
            async_to_sync(channel_layer.group_send)(channel, notification)

        transaction.on_commit(trigger)
