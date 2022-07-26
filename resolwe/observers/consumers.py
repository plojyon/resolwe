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
from .protocol import CHANGE_TYPE_DELETE, GROUP_SESSIONS


class ClientConsumer(JsonWebsocketConsumer):
    """Consumer for client communication."""

    def websocket_connect(self, message):
        """Called when WebSocket connection is established."""
        session_id = self.scope["url_route"]["kwargs"]["session_id"]
        self.session_id = session_id

        # Accept the connection
        super().websocket_connect(message)

    @property
    def groups(self):
        """Groups this channel should add itself to."""
        if not hasattr(self, "session_id"):
            return []
        return [GROUP_SESSIONS.format(session_id=self.session_id)]

    def disconnect(self, code):
        """Called when WebSocket connection is closed."""
        Observer.objects.filter(session_id=self.session_id).delete()
        self.close()

    def observers_item_update(self, msg):
        """Called when an item update is received."""
        subscription_ids = list(
            Observer.get_interested(
                table=msg["table"],
                resource_pk=msg["primary_key"],
                change_type=msg["type_of_change"],
            )
            .values_list("subscription_id", flat=True)
            .distinct()
        )

        if msg["type_of_change"] == CHANGE_TYPE_DELETE:
            # The observed object was either deleted or the user lost permissions.
            observer = Observer.objects.filter(
                session_id=self.session_id,
                table=msg["table"],
                resource_pk=msg["primary_key"],
                # change_type = Any,
            )
            # Assure we don't stay subscribed to an illegal object.
            if observer.exists():
                observer.delete()

        for subscription_id in subscription_ids:
            self.send_json(
                {
                    "subscription_id": subscription_id,
                    "primary_key": msg["primary_key"],
                    "type_of_change": msg["type_of_change"],
                }
            )
