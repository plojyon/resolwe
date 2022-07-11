from django.db import models
from django.conf import settings
from resolwe.permissions.models import PermissionModel

from .protocol import CHANGE_TYPE_CREATE, CHANGE_TYPE_UPDATE, CHANGE_TYPE_DELETE


class Observer(models.Model):
    """State of an observer.

    Monitors a single resource (instance of a model) for several clients.
    """

    CHANGE_TYPES = (
        (CHANGE_TYPE_CREATE, "create"),
        (CHANGE_TYPE_UPDATE, "update"),
        (CHANGE_TYPE_DELETE, "delete"),
    )

    id = models.CharField(primary_key=True, max_length=64)

    # table of the observed resource
    table = models.CharField(max_length=100)
    # primary key of the observed resource (null if watching the whole table)
    resource_pk = models.IntegerField(null=True)
    change_type = models.CharField(choices=CHANGE_TYPES, max_length=6)
    subscribers = models.ManyToManyField("Subscriber")

    permission_models = models.ManyToManyField(PermissionModel)

    def __str__(self):
        return "id={id}".format(id=self.id)

    class Meta:
        unique_together = ("table", "resource_pk", "change_type")


class Subscriber(models.Model):
    """Subscriber to an observer.

    This is in 1:1 correspondence to a client (a single browser tab).
    """

    session_id = models.CharField(primary_key=True, max_length=100)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "session_id={session_id}".format(session_id=self.session_id)
