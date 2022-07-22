from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from django.db import models
from django.db.models import Q

from .models import Observer
from .protocol import (
    CHANGE_TYPE_CREATE,
    CHANGE_TYPE_DELETE,
    CHANGE_TYPE_UPDATE,
    GROUP_SESSIONS,
    TYPE_ITEM_UPDATE,
)


def observed_list(original=lambda: None):
    """Subscribe to the table being listed, then list the table."""

    def wrapped(self, request, *args, **kwargs):
        response = original(self, request, *args, **kwargs)
        print("Requesting", request)
        print("Headers", response.headers)
        print("Text", response.content)

        # try:
        #     session_id = request.kwargs.pop("observe")
        #     ids = request.kwargs["ids"]
        #     # TODO: what if 'ids' is not in request.kwargs?
        #
        #     # subscribe(session_id, ids, request.user, ...)
        # except:
        #     pass  # client doesn't want to observe

        return response

    return wrapped


def observed_retrieve(original=lambda: None):
    """Subscribe to the model being retrieved, then retrieve the model."""


def observable(cls):
    """Make a ViewSet observable."""

    if hasattr(cls, "list"):
        setattr(cls, "list", observed_list(cls.list))
    # if hasattr(cls, "retrieve"):
    #     setattr(cls, "retrieve", observed_retrieve(cls.retrieve))

    return cls
