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

    if instance._meta.db_table == Data._meta.db_table:
        print("sending signal for", change_type)

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
    change = CHANGE_TYPE_CREATE if created else CHANGE_TYPE_UPDATE

    if not created and instance._state.adding:
        return

    if instance._meta.db_table == Data._meta.db_table:
        print(
            "post-save of",
            instance,
            "called with created =",
            created,
            " instance._state.adding =",
            instance._state.adding,
        )
        print(
            "registering on_commit for change_type",
            change,
            "on transaction",
            transaction,
        )

    transaction.on_commit(lambda: notify(instance, change))


@dispatch.receiver(model_signals.post_delete)
def model_post_delete(sender, instance, **kwargs):
    transaction.on_commit(lambda: notify(instance, CHANGE_TYPE_DELETE))


# this never happens:
# @dispatch.receiver(model_signals.pre_save)
# def model_pre_save(sender, instance, created=False, **kwargs):
#     if not created:
#         return
#     transaction.on_commit(lambda: notify(instance, CHANGE_TYPE_CREATE))
