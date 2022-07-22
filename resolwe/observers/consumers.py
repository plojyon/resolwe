import asyncio
import collections
import json
import pickle

from channels.consumer import AsyncConsumer
from channels.db import database_sync_to_async
from channels.generic.websocket import JsonWebsocketConsumer

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.db.models import Q

from resolwe.permissions.models import PermissionGroup

from .models import Observer
from .protocol import *


class ClientConsumer(JsonWebsocketConsumer):
    """Consumer for client communication."""

    def websocket_connect(self, message):
        """Called when WebSocket connection is established."""
        self.session_id = self.scope["url_route"]["kwargs"]["subscriber_id"]

        try:
            self.user = self.scope["user"]
            if not isinstance(self.scope["user"], get_user_model()):
                raise KeyError
        except KeyError:
            self.close(code=3000)  # Unauthorized
            return

        # Accept the connection
        super().websocket_connect(message)

    @property
    def groups(self):
        """Groups this channel should add itself to."""
        if not hasattr(self, "session_id"):
            return []

        return [GROUP_SESSIONS.format(session_id=self.session_id)]

    def receive_json(self, content):
        """Called when JSON data is received."""
        # TODO: verify client has permission to subscribe
        table = content["table"]
        type_of_change = content["type_of_change"]
        if "primary_key" in content:
            primary_key = content["primary_key"]
        else:
            primary_key = None

        observer, _ = Observer.objects.get_or_create(
            table=table,
            resource_pk=primary_key,
            change_type=type_of_change,
            session_id=self.session_id,
            user=self.user,
        )
        if content["action"] == "subscribe":
            observer.save()
        else:
            observer.delete()

    def disconnect(self, code):
        """Called when WebSocket connection is closed."""
        Observer.objects.filter(session_id=self.session_id).delete()
        self.close()

    def observers_item_update(self, msg):
        """Called when an item update is received."""

        # We cannot detect permissions for a deleted object, but if it was being
        # observed specifically (not the whole table), then we must have had
        # permissions to view it.
        observer = Observer.objects.filter(
            session_id=self.session_id,
            table=msg["table"],
            resource_pk=msg["primary_key"],
        )
        if msg["type_of_change"] == CHANGE_TYPE_DELETE and observer.exists():
            observer.delete()  # delete the observer afterwards

        # # If an object that we can't see is being observed, unsubscribe automatically
        # if not has_permission:
        #     print("deleting", len(observer), "observers:", list(observer))
        #     observer.delete()

        self.send_json(
            {
                "table": msg["table"],  # model._meta.db_table
                "primary_key": msg["primary_key"],
                "type_of_change": msg["type_of_change"],
            }
        )
