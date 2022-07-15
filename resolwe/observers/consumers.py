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

        model = apps.get_model(app_label=msg["app_label"], model_name=msg["model_name"])
        has_permission = (
            model.objects.filter(pk=msg["primary_key"])
            .filter_for_user(user=self.user)
            .exists()
        )

        if has_permission:
            self.send_json(
                {
                    "table": model._meta.db_table,  # msg["table"],
                    "primary_key": msg["primary_key"],
                    "type_of_change": msg["type_of_change"],
                }
            )
