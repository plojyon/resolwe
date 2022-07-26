import logging

from asgiref.sync import async_to_sync
from channels.exceptions import ChannelFull
from channels.layers import get_channel_layer

from django import dispatch
from django.db import transaction
from django.db.models import Q
from django.db.models import signals as model_signals

from django_priority_batch import PrioritizedBatcher

from resolwe.flow.models import Data
from resolwe.permissions.models import (
    Permission,
    PermissionGroup,
    PermissionModel,
    PermissionObject,
)

from .models import Observer
from .protocol import *

# Global 'in migrations' flag to skip certain operations during migrations.
IN_MIGRATIONS = False


def notification(instance, change_type):
    return {
        "type": TYPE_ITEM_UPDATE,
        "table": instance._meta.db_table,
        "type_of_change": change_type,
        "primary_key": str(instance.pk),
        "app_label": instance._meta.app_label,
        "model_name": instance._meta.object_name,
    }


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


def notify(instance, change_type):
    """Register on_commit calls to notify interested observers of a change."""
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

        notify2(observer.session_id, instance, change_type)


def notify2(session_id, instance, change_type):
    channel = GROUP_SESSIONS.format(session_id=session_id)

    # Define a callback, but save variable values
    def trigger(
        channel_layer=get_channel_layer(),
        channel=channel,
        instance=instance,
        change_type=change_type,
    ):
        async_to_sync(channel_layer.send)(channel, notification(instance, change_type))

    transaction.on_commit(trigger)


@dispatch.receiver(model_signals.post_save)
def observe_model_modification(sender, instance, created=False, **kwargs):
    global IN_MIGRATIONS
    if IN_MIGRATIONS:
        return

    # Create signals will be caught when the PermissionModel is added.
    if created:
        return

    notify(instance, CHANGE_TYPE_UPDATE)


@dispatch.receiver(model_signals.pre_delete)
def observe_model_deletion(sender, instance, **kwargs):
    global IN_MIGRATIONS
    if IN_MIGRATIONS:
        return
    notify(instance, CHANGE_TYPE_DELETE)


@dispatch.receiver(model_signals.pre_save)
def detect_permission_change(sender, instance, **kwargs):
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
                announce_permission_changes(inst, gains, losses)

    elif isinstance(instance, PermissionObject):
        # Create signals will be caught when the PermissionModel is added.
        if instance._state.adding:
            return

        saved_instance = type(instance).objects.get(pk=instance.pk)
        old_perm_group = instance.permission_group
        new_perm_group = saved_instance.permission_group

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
        announce_permission_changes(instance, gains, losses)


def announce_permission_changes(instance, gains, losses):
    """Register on_commit calls to notify observers that permissions changed.

    Given an instance and an array of user_ids who gained/lost permissions for
    it, all relevant observers will be notified of instance creation/deletion.
    """
    channel_layer = get_channel_layer()
    for change_type, user_ids in (
        (CHANGE_TYPE_CREATE, gains),
        (CHANGE_TYPE_DELETE, losses),
    ):
        if len(user_ids) == 0:
            continue

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
            notify2(session_id, instance, change_type)
