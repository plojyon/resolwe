"""ORM signal handlers."""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from django import dispatch
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import signals as model_signals

from resolwe.permissions.models import Permission

from .models import Observer, Subscription
from .protocol import (
    CHANGE_TYPE_CREATE,
    CHANGE_TYPE_DELETE,
    CHANGE_TYPE_UPDATE,
    GROUP_SESSIONS,
    TYPE_ITEM_UPDATE,
    post_permission_changed,
    pre_permission_changed,
)

# Global 'in migrations' flag to ignore signals during migrations.
# Signal handlers that access the database can crash the migration process.
IN_MIGRATIONS = False


@dispatch.receiver(model_signals.pre_migrate)
def model_pre_migrate(*args, **kwargs):
    """Set 'in migrations' flag."""
    global IN_MIGRATIONS
    IN_MIGRATIONS = True


@dispatch.receiver(model_signals.post_migrate)
def model_post_migrate(*args, **kwargs):
    """Clear 'in migrations' flag."""
    global IN_MIGRATIONS
    IN_MIGRATIONS = False


@dispatch.receiver(pre_permission_changed)
def prepare_permission_change(instance, **kwargs):
    """Store old permissions for an object whose permissions are about to change."""
    global IN_MIGRATIONS
    if IN_MIGRATIONS:
        return

    instance._old_viewers = instance.users_with_permission(Permission.VIEW)


@dispatch.receiver(post_permission_changed)
def handle_permission_change(instance, **kwargs):
    """Compare permissions for an object whose permissions changed."""
    global IN_MIGRATIONS
    if IN_MIGRATIONS:
        return

    new = instance.users_with_permission(Permission.VIEW)
    old = instance._old_viewers

    gains = new - old
    losses = old - new
    route_permission_changes(instance, gains, losses)


def route_instance_changes(instance, change_type):
    """Route a notification about an instance change to the appropriate observers."""
    global IN_MIGRATIONS
    if IN_MIGRATIONS:
        return

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
        send_notification(subscriber.session_id, instance, change_type)


def route_permission_changes(instance, gains, losses):
    """Route a notification about a permission change to the appropriate observers.

    Given an instance and a set of user_ids who gained/lost permissions for it,
    all relevant observers will be notified of the instance's creation/deletion.
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
            content_type=ContentType.objects.get_for_model(type(instance)),
            object_id=instance.pk,
        )
        session_ids = set(
            Subscription.objects.filter(observers__in=interested)
            .filter(user__in=user_ids)
            .values_list("session_id", flat=True)
            .distinct()
        )

        for session_id in session_ids:
            send_notification(session_id, instance, change_type)


def send_notification(session_id, instance, change_type):
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
        async_to_sync(channel_layer.send)(channel, notification)

    transaction.on_commit(trigger)


@dispatch.receiver(model_signals.post_save)
def observe_model_modification(sender, instance, created=False, **kwargs):
    """Receive model updates."""
    global IN_MIGRATIONS
    if IN_MIGRATIONS:
        return

    # Create signals will be caught when the PermissionModel is added.
    if created:
        return

    route_instance_changes(instance, CHANGE_TYPE_UPDATE)


@dispatch.receiver(model_signals.pre_delete)
def observe_model_deletion(sender, instance, **kwargs):
    """Receive model deletions."""
    global IN_MIGRATIONS
    if IN_MIGRATIONS:
        return

    route_instance_changes(instance, CHANGE_TYPE_DELETE)
