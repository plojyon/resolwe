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

# Logger.
logger = logging.getLogger(__name__)

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


def notify_observers(type_of_change, table, instance):
    """Transmit ORM table change notification.

    :param type_of_change: Change type
    :param table: Name of the table that has changed
    :param instance: Affected object instance
    """

    if IN_MIGRATIONS:
        return

    # Don't propagate events when there are no observers to receive them.
    if not Observer.objects.filter(table=table).exists():
        return

    # Check if this is a permission change.
    if hasattr(instance, "_old_permissions"):
        async_to_sync(get_channel_layer().send)(
            CHANNEL_MAIN,
            {
                "type": TYPE_PERM_UPDATE,
                "permission_group": instance.permission_group.pk,
                "old": instance._old_permissions,
                "new": instance._new_permissions,
            },
        )

    # Send the item update signal.
    try:
        async_to_sync(get_channel_layer().send)(
            CHANNEL_MAIN,
            {
                "type": TYPE_ITEM_UPDATE,
                "table": table,
                "type_of_change": type_of_change,
                "primary_key": str(instance.pk),
                "app_label": instance._meta.app_label,
                "model_name": instance._meta.object_name,
            },
        )
    except ChannelFull:
        logger.exception("Unable to notify workers.")


@dispatch.receiver(model_signals.post_save)
def model_post_save(sender, instance, created=False, **kwargs):
    """Signal emitted after any model is saved via Django ORM.

    :param sender: Model class that was saved
    :param instance: The actual instance that was saved
    :param created: True if a new row was created
    """
    if hasattr(instance, "_old_permissions"):
        new_data = permissions_to_json(instance.permission_group)
        instance._new_permissions = new_data

    def notify():
        table = sender._meta.db_table
        if created:
            notify_observers(CHANGE_TYPE_CREATE, table, instance)
        else:
            notify_observers(CHANGE_TYPE_UPDATE, table, instance)

    transaction.on_commit(notify)


@dispatch.receiver(model_signals.post_delete)
def model_post_delete(sender, instance, **kwargs):
    """Signal emitted after any model is deleted via Django ORM.

    :param sender: Model class that was deleted
    :param instance: The actual instance that was removed
    """

    def notify():
        table = sender._meta.db_table
        notify_observers(CHANGE_TYPE_DELETE, table, instance)

    transaction.on_commit(notify)


# TODO: disregard m2m changes?
# @dispatch.receiver(model_signals.m2m_changed)
# def model_m2m_changed(sender, instance, action, **kwargs):
#     """
#     Signal emitted after any M2M relation changes via Django ORM.
#
#     :param sender: M2M intermediate model
#     :param instance: The actual instance that was saved
#     :param action: M2M action
#     """
#
#     if sender._meta.app_label == "rest_framework_reactive":
#         # Ignore own events.
#         return
#
#     def notify():
#         table = sender._meta.db_table
#         if action == "post_add":
#             notify_observers(table, CHANGE_TYPE_CREATE)
#         elif action in ("post_remove", "post_clear"):
#             notify_observers(table, CHANGE_TYPE_DELETE)
#
#     transaction.on_commit(notify)


def permissions_to_json(perm_group):
    """TODO: docstring."""
    # [{user, group, value}, ...]
    permissions = []
    perm_models = PermissionModel.objects.get(permission_group=perm_group)
    for perm in perm_models:
        permissions.append(
            {"user": perm.user, "group": perm.group, "value": perm.value}
        )

    # Don't actually stringify this yet; let Channels do it
    return permissions


@dispatch.receiver(model_signals.pre_save, sender=PermissionObject)
def permission_model_pre_change(sender, instance, created=False, **kwargs):
    """Note the difference in permission value before changing any model with permissions."""
    if created:
        return

    perm_group = sender.objects.get(pk=instance.pk).permission_group
    old_data = permissions_to_json(perm_group)
    instance._old_permissions = old_data


@dispatch.receiver(model_signals.pre_save, sender=PermissionModel)
def permission_model_pre_change(sender, instance, created=False, **kwargs):
    """Note the difference in permission value before saving a PermissionModel."""
    old_data = permissions_to_json(instance.permission_group)
    instance._old_permissions = old_data


"""
def on_save_PermissionGroup(modified_pg):
    set = {}
    for o in observers.filter(observing=modified_pg):
        for sub in o.subscribers:
            set.add(sub)

    old_pg = PermissionGroup.objects.get(pk=modified_pg)
    data = dict()
    for sub in set:
        old_perms = sub.get_permission(old_pg)
        data[sub.pk] = old_perms

    instance.data = data

def on_save_PermissionModel(modified_pm):
    pg = modified_pm.permission_group
    on_save_PermissionGroup(pg)

"""
