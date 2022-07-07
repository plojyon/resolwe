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

from .connection import get_queryobserver_settings
from .models import Observer, Subscriber
from .observer import QueryObserver
from .protocol import *


class MainConsumer(AsyncConsumer):
    """Consumer for polling observers."""

    async def observer_orm_notify(self, message):
        """Process notification from ORM."""

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

        for session_id in subscribers:
            # overwrite the message type, everything else stays the same
            message["type"] = TYPE_ITEM_UPDATE
            group = GROUP_SESSIONS.format(session_id=session_id)
            await self.channel_layer.send(group, message)


class ClientConsumer(JsonWebsocketConsumer):
    """Client consumer."""

    def websocket_connect(self, message):
        """Called when WebSocket connection is established."""
        self.session_id = self.scope["url_route"]["kwargs"]["subscriber_id"]
        self.user = self.scope["user"]

        # Accept the connection
        super().websocket_connect(message)

        # Create new subscriber object
        Subscriber.objects.get_or_create(session_id=self.session_id, user=self.user)

    def receive_json(self, content):
        """Called when JSON data is received."""
        table = content["table"]
        type_of_change = content["type_of_change"]
        if "primary_key" in content:
            primary_key = content["primary_key"]
        else:
            primary_key = None

        observer = Observer.objects.get_or_create(
            table=table, resource=primary_key, change_type=type_of_change
        )
        subscriber = Subscriber.objects.get(session_id=self.session_id)

        if content["action"] == "subscribe":
            observer.subscribers.add(subscriber)
        else:
            observer.subscribers.remove(subscriber)

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

    def observer_update(self, msg):
        """Called when update is received."""

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
        # TODO: monitor for permission changes

        # with connection.cursor() as cursor:
        #     cursor.execute(
        #         "SELECT permission_group FROM %s WHERE %s = %s",
        #         [table, pk_column, primary_key],
        #     )
        #     row = cursor.fetchone()
        #
        # # TODO: what if len(row) == 0?
        # PermissionGroup.objects.get(id=row[0])
