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


def _notify(instance, change_type):
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
    change_type = CHANGE_TYPE_CREATE if created else CHANGE_TYPE_UPDATE
    transaction.on_commit(lambda: _notify(instance, change_type))


@dispatch.receiver(model_signals.post_delete)
def model_post_delete(sender, instance, **kwargs):
    transaction.on_commit(lambda: _notify(instance, CHANGE_TYPE_DELETE))
