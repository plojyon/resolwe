"""ORM signal handlers."""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from django import dispatch
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import signals as model_signals

from resolwe.permissions.models import PermissionModel, PermissionObject

from .models import Observer, Subscription
from .protocol import (
    CHANGE_TYPE_CREATE,
    CHANGE_TYPE_DELETE,
    CHANGE_TYPE_UPDATE,
    GROUP_SESSIONS,
    TYPE_ITEM_UPDATE,
)

# Global 'in migrations' flag to ignore signals during migrations.
# Signals handlers that access the database will crash the migration process.
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


@dispatch.receiver(model_signals.pre_save)
def detect_permission_change(sender, instance, created=False, **kwargs):
    """Handle updates for PermissionObjects and PermissionModels.

    The goal is to detect when any user gains or loses permissions to an object.
    save signal ->
        PermissionModel
            CREATE/UPDATE .. for every user affected by this PM, compare the old
                and new permission value. If it changed from 0 to non-0 or vice versa,
                notify the users.
            DELETE .. do nothing.
        PermissionObject
            CREATE .. do nothing, permissions haven't changed.
            UPDATE
                PG changed .. compare permissions for all subscribing users.
                PG unchanged .. do nothing, we must have changed another field.
            DELETE .. do nothing, delete signals are caught at PermissionModel level.
        PermissionGroup .. do nothing, a PG can't be modified anyway.
    """
    global IN_MIGRATIONS
    if IN_MIGRATIONS:
        return

    if isinstance(instance, PermissionModel):
        gains = set()
        losses = set()

        # Find users affected by this PermissionModel.
        if instance.user is not None:
            relevant_users = [instance.user]
        else:
            relevant_users = list(
                get_user_model().objects.filter(groups__pk=instance.group.pk)
            )

        # For every affected user, calculate their former and current permissions.
        for user in relevant_users:
            old_permission = instance.permission_group.get_permission(user)
            if old_permission > 0 and instance.value == 0:
                losses.add(user.pk)
            elif old_permission == 0 and instance.value > 0:
                gains.add(user.pk)

        # In case of no changes, return.
        if len(gains) == 0 and len(losses) == 0:
            return

        # Find all relevant PermissionObjects and announce permission changes.
        for cls in PermissionObject.__subclasses__():
            for inst in cls.objects.filter(permission_group=instance.permission_group):
                route_permission_changes(inst, gains, losses)

    elif isinstance(instance, PermissionObject):
        saved_instances = type(instance).objects.filter(pk=instance.pk)

        # Create signals will be caught when the PermissionModel is added.
        if saved_instances.count() == 0:
            return

        saved_instance = saved_instances[0]
        old_perm_group = instance.permission_group
        new_perm_group = saved_instance.permission_group

        # In case either PermissionGroup doesn't exist, return.
        if old_perm_group is None or new_perm_group is None:
            return

        # In case of no changes, return.
        if old_perm_group.pk == new_perm_group.pk:
            return

        # Calculate who gained and lost permissions to the object.
        gains = set()
        losses = set()
        interested = Observer.get_interested(
            content_type=ContentType.objects.get_for_model(type(instance)),
            object_id=instance.pk,
        )
        for subscriber in Subscription.objects.filter(observers__in=interested):
            new_permissions = old_perm_group.get_permission(subscriber.user)
            old_permissions = new_perm_group.get_permission(subscriber.user)

            if old_permissions == 0 and new_permissions > 0:
                gains.add(subscriber.user)
            if old_permissions > 0 and new_permissions == 0:
                losses.add(subscriber.user)

        # Announce to relevant observers.
        route_permission_changes(instance, gains, losses)
