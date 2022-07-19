import logging

from asgiref.sync import async_to_sync
from channels.exceptions import ChannelFull
from channels.layers import get_channel_layer
from django import dispatch
from django.db import transaction
from django.db.models import signals as model_signals
from django_priority_batch import PrioritizedBatcher
from resolwe.permissions.models import (
    PermissionModel,
    Permission,
    PermissionGroup,
    PermissionObject,
)
from .models import Observer
from .protocol import *
from .wrappers import get_observers
from resolwe.flow.models import Data
from django.db.models import Q

# Global 'in migrations' flag to skip certain operations during migrations.
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


def notify(instance, change_type):
    global IN_MIGRATIONS
    if IN_MIGRATIONS:
        return

    message = {
        "type": TYPE_ITEM_UPDATE,
        "table": instance._meta.db_table,
        "type_of_change": change_type,
        "primary_key": str(instance.pk),
        "app_label": instance._meta.app_label,
        "model_name": instance._meta.object_name,
    }
    observers = get_observers(change_type, instance._meta.db_table, instance.pk)

    # Forward the message to the appropriate groups.
    channel_layer = get_channel_layer()
    for observer in observers:
        group = GROUP_SESSIONS.format(session_id=observer.session_id)
        async_to_sync(channel_layer.send)(group, message)


@dispatch.receiver(model_signals.post_save)
def model_post_save(sender, instance, created=False, **kwargs):
    global IN_MIGRATIONS
    if IN_MIGRATIONS:
        return

    change = CHANGE_TYPE_CREATE if created else CHANGE_TYPE_UPDATE
    transaction.on_commit(lambda: notify(instance, change))


@dispatch.receiver(model_signals.post_delete)
def model_post_delete(sender, instance, **kwargs):
    global IN_MIGRATIONS
    if IN_MIGRATIONS:
        return
    transaction.on_commit(lambda: notify(instance, CHANGE_TYPE_DELETE))


@dispatch.receiver(model_signals.pre_save)
def model_pre_save(sender, instance, created=False, **kwargs):
    global IN_MIGRATIONS
    if IN_MIGRATIONS:
        return

    # created is always False. Use instance._state.adding
    if instance._state.adding:
        return
        if isinstance(instance, PermissionModel):
            instance = instance.permission_group
        else:
            return

    if isinstance(instance, PermissionObject):
        # or isinstance(instance, PermissionModel):
        saved_instance = type(instance).objects.get(pk=instance.pk)
        old_perm_group = instance.permission_group
        new_perm_group = saved_instance.permission_group

        # Calculate who gained and lost permissions to the object.
        gains, losses = permission_diff(old_perm_group, new_perm_group)

        print(
            "pre-save on",
            instance,
            "with created =",
            instance._state.adding,
            "has (gains,losses) = ",
            (gains, losses),
        )

        # Announce to relevant observers
        announce_permission_changes(instance, gains, losses)

        # Delete redundant observers.
        Observer.objects.filter(
            user__in=losses, table=instance._meta.db_table, resource_pk=instance.pk
        ).delete()
    elif isinstance(instance, PermissionGroup):
        saved_instance = type(instance).objects.get(pk=instance.pk)

        # Calculate who gained and lost permissions to the object.
        gains, losses = permission_diff(instance, saved_instance)

        print(
            "pre-save on",
            instance,
            "->",
            saved_instance,
            "with created =",
            instance._state.adding,
            "has (gains,losses) = ",
            (gains, losses),
        )

        # Announce to relevant observers
        announce_permission_changes(instance, gains, losses)


def permission_diff(old_perm_group, new_perm_group):
    """Calculate the difference in permissions given two PermissionGroups.

    Accept two PermissionGroup objects and return two lists. The first list is
    user_ids of users who gained permissions (0 to >0), and the second list is
    user_ids of users who lost permissions (>0 to 0).
    """
    old_permissions = dict()
    new_permissions = dict()
    for observer in Observer.objects.all():
        new_permissions[observer.user.pk] = old_perm_group.get_permission(observer.user)
        old_permissions[observer.user.pk] = new_perm_group.get_permission(observer.user)

    # Calculate the list of people who lost/gained permissions
    gains = []
    losses = []
    # Keys in both readings may not match in an edge case where a subscription
    # was created / destroyed while a transaction was open. We'll ignore differences.
    common_keys = set(new_permissions.keys()).intersection(set(old_permissions.keys()))
    for key in common_keys:
        if old_permissions[key] == 0 and new_permissions[key] > 0:
            gains.append(key)
        if old_permissions[key] > 0 and new_permissions[key] == 0:
            losses.append(key)
    return (gains, losses)


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

        message = {
            "type": TYPE_ITEM_UPDATE,
            "table": instance._meta.db_table,
            "type_of_change": change_type,
            "primary_key": str(instance.pk),
            "app_label": instance._meta.app_label,
            "model_name": instance._meta.object_name,
        }
        session_ids = list(
            Observer.objects.filter(
                user__in=user_ids,
                table=instance._meta.db_table,
                resource_pk=instance.pk,
            )
            .values_list("session_id", flat=True)
            .distinct()
        )
        for session_id in session_ids:
            channel = GROUP_SESSIONS.format(session_id=session_id)

            transaction.on_commit(
                lambda: async_to_sync(channel_layer.send)(channel, message)
            )
