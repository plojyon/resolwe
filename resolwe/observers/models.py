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
    TYPE_PERM_UPDATE,
)


class ObservableQuerySet(models.QuerySet):
    """All observable models inherit from this."""

    def _get_observers(self, table, pk=None):
        """Find all observers watching for changes of a given item/table."""
        query = Q(table=table, change_type=CHANGE_TYPE_CREATE)
        query &= Q(resource_pk=pk) | Q(resource_pk__isnull=True)
        return list(Observer.objects.filter(query))

    def create(self, *args, **kwargs):
        created = super().create(*args, **kwargs)

        # The message to be sent to observers.
        message = {
            "type": TYPE_ITEM_UPDATE,
            "table": created._meta.db_table,
            "type_of_change": CHANGE_TYPE_CREATE,
            "primary_key": str(created.pk),
            "app_label": created._meta.app_label,
            "model_name": created._meta.object_name,
        }

        observers = self._get_observers(created._meta.db_table, created.pk)

        # Forward the message to the appropriate groups.
        channel_layer = get_channel_layer()
        for observer in observers:
            group = GROUP_SESSIONS.format(session_id=observer.session_id)
            async_to_sync(channel_layer.send)(group, message)

        return created


class Observer(models.Model):
    """State of an observer."""

    CHANGE_TYPES = (
        (CHANGE_TYPE_CREATE, "create"),
        (CHANGE_TYPE_UPDATE, "update"),
        (CHANGE_TYPE_DELETE, "delete"),
    )

    # table of the observed resource
    table = models.CharField(max_length=100)
    # primary key of the observed resource (null if watching the whole table)
    resource_pk = models.IntegerField(null=True)
    change_type = models.CharField(choices=CHANGE_TYPES, max_length=6)
    session_id = models.CharField(max_length=100)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "table={table} resource_pk={res} change={change} session_id={session_id}".format(
            table=self.table,
            res=self.resource_pk,
            change=self.change_type,
            session_id=self.session_id,
        )

    class Meta:
        unique_together = ("table", "resource_pk", "change_type", "session_id")
