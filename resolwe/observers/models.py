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

# def _queryset_factory(fallback=models.QuerySet):
#     return type(
#         "observable_qs",
#         (fallback,),
#         {
#             # "save": lambda self, *args, **kwargs: _observed_save(self, *args, **kwargs),
#             # "objects": _queryset_factory(cls.objects),
#         },
#     )


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
