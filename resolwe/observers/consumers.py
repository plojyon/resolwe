import asyncio
import collections
import json
import pickle

from django.apps import apps
from django.db import connection
from django.db.models import Q
from channels.consumer import AsyncConsumer
from channels.db import database_sync_to_async
from channels.generic.websocket import JsonWebsocketConsumer
from django.core.cache import cache
from resolwe.permissions.models import PermissionGroup

from .models import Observer, Subscriber
from .protocol import *


class MainConsumer(AsyncConsumer):
    """Consumer for dispatching signals to interested client consumers."""

    async def observers_item_update(self, message):
        """Process ORM item updates."""

        @database_sync_to_async
        def get_subscribers(table, item, type_of_change):
            """Find all subscribers watching a given item in a table."""
            query = Q(observers__table=table, observers__change_type=type_of_change)
            query &= Q(observers__resource=item) | Q(observers__resource__isnull=True)
            return list(Subscriber.objects.filter(query))

        table = message["table"]
        item = message["primary_key"]
        type_of_change = message["type_of_change"]
        subscribers = await get_subscribers(table, item, type_of_change)

        # forward the message to the appropriate groups
        for session_id in subscribers:
            group = GROUP_SESSIONS.format(session_id=session_id)
            await self.channel_layer.send(group, message)

    async def observers_permission_update(self, message):
        """Process ORM permission updates."""

        @database_sync_to_async
        def get_subscribers(group_pk):
            """Find all subscribers watching the item whose permission changed."""
            subs = Subscriber.objects.filter(observer__permission_group__pk=group_pk)
            return list(subs)

        group_pk = message["permission_group"]
        subscribers = await get_subscribers(group_pk)

        # forward the message to the appropriate groups
        for session_id in subscribers:
            group = GROUP_SESSIONS.format(session_id=session_id)
            await self.channel_layer.send(group, message)


class ClientConsumer(JsonWebsocketConsumer):
    """Consumer for client communication."""

    def websocket_connect(self, message):
        """Called when WebSocket connection is established."""
        self.session_id = self.scope["url_route"]["kwargs"]["subscriber_id"]
        self.user = self.scope["user"]

        # Accept the connection
        super().websocket_connect(message)

        # Create new subscriber object
        Subscriber.objects.get_or_create(session_id=self.session_id, user=self.user)

    @property
    def groups(self):
        """Groups this channel should add itself to."""
        if not hasattr(self, "session_id"):
            return []

        return [GROUP_SESSIONS.format(session_id=self.session_id)]

    def disconnect(self, code):
        """Called when WebSocket connection is closed."""
        Subscriber.objects.filter(session_id=self.session_id).delete()
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
                    "table": msg["table"],
                    "primary_key": msg["primary_key"],
                    "type_of_change": msg["type_of_change"],
                }
            )

    def observers_permission_update(self, msg):
        """Called when a PermissionModel is updated or created."""
        old = msg["old"]
        new = msg["new"]
        group = msg["permission_group"]
        # TODO: monitor for permission changes
