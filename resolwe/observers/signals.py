"""ORM signal handlers."""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from django import dispatch
from django.db import transaction
from django.db.models import signals as model_signals

from resolwe.permissions.models import PermissionModel, PermissionObject

from .models import Observer
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
        table=instance._meta.db_table,
        resource_pk=instance.pk,
    )

    # Forward the message to the appropriate groups.
    for observer in observers:
        has_permission = (
            type(instance)
            .objects.filter(pk=instance.pk)
            .filter_for_user(user=observer.user)
            .exists()
        )
        if not has_permission:
            continue

        # Register on_commit callbacks to send the signals.
        send_notification(observer.session_id, instance, change_type)


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
        session_ids = set(
            Observer.get_interested(
                table=instance._meta.db_table,
                resource_pk=instance.pk,
            )
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
        "table": instance._meta.db_table,
        "type_of_change": change_type,
        "primary_key": str(instance.pk),
        "app_label": instance._meta.app_label,
        "model_name": instance._meta.object_name,
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
def detect_permission_change(sender, instance, **kwargs):
    """Receive permission updates."""
    global IN_MIGRATIONS
    if IN_MIGRATIONS:
        return

    if isinstance(instance, PermissionModel):
        gains = set()
        losses = set()
        if instance.user is not None:
            relevant_users = [instance.user]
        else:
            relevant_users = list(instance.group.users)

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
        # Create signals will be caught when the PermissionModel is added.
        if instance._state.adding:
            return

        saved_instance = type(instance).objects.get(pk=instance.pk)
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
        for observer in Observer.objects.all():
            new_permissions = old_perm_group.get_permission(observer.user)
            old_permissions = new_perm_group.get_permission(observer.user)

            if old_permissions == 0 and new_permissions > 0:
                gains.add(observer.user)
            if old_permissions > 0 and new_permissions == 0:
                losses.add(observer.user)

        # Announce to relevant observers.
        route_permission_changes(instance, gains, losses)
