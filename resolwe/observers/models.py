"""The model Observer model."""
import random

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from django.conf import settings
from django.db import models
from django.db.models import Q

from resolwe.permissions.models import PermissionModel

from .protocol import (
    CHANGE_TYPE_CREATE,
    CHANGE_TYPE_DELETE,
    CHANGE_TYPE_UPDATE,
    GROUP_SESSIONS,
    TYPE_ITEM_UPDATE,
)


def get_random_hash():
    """Generate a random 256-bit number as a hex string."""
    return hex(random.randint(0, 2**128))[2:]


class Observer(models.Model):
    """State of a model observer."""

    CHANGE_TYPES = (
        (CHANGE_TYPE_CREATE, "create"),
        (CHANGE_TYPE_UPDATE, "update"),
        (CHANGE_TYPE_DELETE, "delete"),
    )

    # Table of the observed resource
    table = models.CharField(max_length=100)
    # Primary key of the observed resource (null if watching the whole table)
    resource_pk = models.IntegerField(null=True)
    change_type = models.CharField(choices=CHANGE_TYPES, max_length=6)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    created = models.DateTimeField(auto_now_add=True)

    # ID of the websocket session (can have multiple observers)
    session_id = models.CharField(max_length=100)
    # Unique ID for the client to remember which subscription a signal belongs to
    subscription_id = models.CharField(
        max_length=32, unique=True, default=get_random_hash
    )

    @classmethod
    def get_interested(cls, table, resource_pk=None, change_type=None):
        """Find all observers watching for changes of a given item/table."""
        query = Q(table=table)
        if change_type is not None:
            query &= Q(change_type=change_type)
        query &= Q(resource_pk=resource_pk) | Q(resource_pk__isnull=True)
        return cls.objects.filter(query)

    def __str__(self):
        return "table={table} resource_pk={res} change={change} session_id={session_id}".format(
            table=self.table,
            res=self.resource_pk,
            change=self.change_type,
            session_id=self.session_id,
        )

    class Meta:
        unique_together = ("table", "resource_pk", "change_type", "session_id")
