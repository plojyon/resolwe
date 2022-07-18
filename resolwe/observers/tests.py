"""Tests for observers."""
import asyncio
import json

import async_timeout
from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import ApplicationCommunicator, WebsocketCommunicator

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, TestCase
from django.urls import path

from rest_framework.test import force_authenticate

from resolwe.flow.models import Data, DescriptorSchema, Process

from .consumers import ClientConsumer
from .models import Observer
from .protocol import (
    CHANGE_TYPE_CREATE,
    CHANGE_TYPE_DELETE,
    CHANGE_TYPE_UPDATE,
    GROUP_SESSIONS,
    TYPE_ITEM_UPDATE,
    TYPE_PERM_UPDATE,
)

from asgiref.sync import async_to_sync

from django.db import transaction


class ConnectionTestCase(TestCase):
    """Tests for verifying the correctness of the Websocket connection."""

    def setUp(self):
        super().setUp()
        self.client_consumer = URLRouter(
            [path("ws/<slug:subscriber_id>", ClientConsumer().as_asgi())]
        )

    async def test_ws_no_auth(self):
        client = WebsocketCommunicator(self.client_consumer, "/ws/test-session")

        connected, details = await client.connect()
        self.assertFalse(connected)
        self.assertEquals(details, 3000)  # code 3000 - unauthorized

        await client.disconnect()


class ObserverTestCase(TransactionTestCase):
    def setUp(self):
        super().setUp()

        self.user = get_user_model().objects.create(
            username="xX-auth3nt1cat0r-Xx",
            email="user@test.com",
            first_name="John",
            last_name="Williams",
        )
        self.user.save()

        self.process = Process.objects.create(
            name="Dummy process", contributor=self.user
        )

        self.client_consumer = URLRouter(
            [path("ws/<slug:subscriber_id>", ClientConsumer().as_asgi())]
        )

    async def clear_channel(self, channel):
        """A hack to clear all uncaught messages from the channel layer."""
        channel_layer = get_channel_layer()
        while True:
            try:
                async with async_timeout.timeout(0.01):
                    await channel_layer.receive(channel)
            except asyncio.exceptions.TimeoutError:
                break

    async def assert_and_propagate_signal(self, signal, channel, client):
        # Check that a signal was generated.
        channel_layer = get_channel_layer()
        async with async_timeout.timeout(1):
            notify = await channel_layer.receive(channel)

        self.assertDictEqual(notify, signal)

        # Propagate notification to worker.
        await client.send_input(notify)

    async def test_ws_subscribe_unsubscribe(self):
        channel = GROUP_SESSIONS.format(session_id="session_28946")
        await self.clear_channel(channel)
        client = WebsocketCommunicator(self.client_consumer, "/ws/session_28946")
        client.scope["user"] = self.user
        connected, _ = await client.connect()
        self.assertTrue(connected)

        async def propagate_data_signal(change):
            await self.assert_and_propagate_signal(
                {
                    "type": TYPE_ITEM_UPDATE,
                    "type_of_change": change,
                    "primary_key": "42",
                    "table": Data._meta.db_table,
                    "app_label": Data._meta.app_label,
                    "model_name": Data._meta.object_name,
                },
                channel,
                client,
            )

        async def await_subscription_count(count):
            """Wait until the number of all subscriptions is equal to count."""

            @database_sync_to_async
            def get_subscription_count():
                return Observer.objects.filter(session_id="session_28946").count()

            async with async_timeout.timeout(1):
                while await get_subscription_count() != count:
                    await asyncio.sleep(0.01)

        await await_subscription_count(0)

        # Subscribe to updates.
        await client.send_to(
            text_data=json.dumps(
                {
                    "action": "subscribe",
                    "table": Data._meta.db_table,
                    "type_of_change": "UPDATE",
                    "primary_key": 42,
                }
            )
        )
        await client.send_to(
            text_data=json.dumps(
                {
                    "action": "subscribe",
                    "table": Data._meta.db_table,
                    "type_of_change": "CREATE",
                    "primary_key": 42,
                }
            )
        )
        # We have to wait for the subscription to register
        await await_subscription_count(2)

        # Create a Data object.
        @database_sync_to_async
        def create_data():
            return Data.objects.create(
                pk=42,
                name="Public data",
                slug="public-data",
                contributor=self.user,
                process=self.process,
                size=0,
            )

        print("gonna make data")
        data = await create_data()
        print("made data")
        await propagate_data_signal(CHANGE_TYPE_CREATE)
        packet = json.loads(await client.receive_from())
        self.assertEquals(packet["table"], "flow_data")
        self.assertEquals(packet["primary_key"], "42")
        self.assertEquals(packet["type_of_change"], "CREATE")

        return await client.disconnect()

        data.name = "name2"
        await database_sync_to_async(data.save)()
        await propagate_data_signal(CHANGE_TYPE_UPDATE)
        packet = json.loads(await client.receive_from())
        self.assertEquals(packet["table"], "flow_data")
        self.assertEquals(packet["primary_key"], "42")
        self.assertEquals(packet["type_of_change"], "UPDATE")

        await database_sync_to_async(data.delete)()
        await propagate_data_signal(CHANGE_TYPE_DELETE)
        packet = json.loads(await client.receive_from())
        self.assertEquals(packet["table"], "flow_data")
        self.assertEquals(packet["primary_key"], "42")
        self.assertEquals(packet["type_of_change"], "DELETE")

        # Unsubscribe from updates.
        await client.send_to(
            text_data=json.dumps(
                {
                    "action": "unsubscribe",
                    "table": Data._meta.db_table,
                    "type_of_change": "UPDATE",
                    "primary_key": 42,
                }
            )
        )
        await await_subscription_count(0)

        await client.disconnect()

    # async def test_0(self):
    #     pass
    #
    # async def test_1(self):
    #     pass
    #
    # async def test_2(self):
    #     pass
    #
    # async def test_3(self):
    #     pass
    #
    # async def test_4(self):
    #     pass
    #
    # async def test_5(self):
    #     pass
    #
    # async def test_6(self):
    #     pass
    #
    # async def test_7(self):
    #     pass
    #
    # async def test_8(self):
    #     pass
    #
    # async def test_9(self):
    #     pass
    #
    # async def test_notifications(self):
    #     return
    #
    #     # Create a single model instance.
    #     @database_sync_to_async
    #     def create_model():
    #         return Data.objects.create(
    #             name="Data object",
    #             contributor=self.user,
    #             process=self.process,
    #             # descriptor_schema=self.descriptor_schema,
    #         )
    #
    #     data = await create_model()
    #     # TODO: assert existance of an observer, has 1 subscriber


# async def test_bla():
#
#     async with async_timeout.timeout(1):
#         # Check that ORM signal was generated.
#         notify = await channel_layer.receive(CHANNEL_MAIN)
#         assert notify["type"] == TYPE_ORM_NOTIFY
#         assert notify["kind"] == ORM_NOTIFY_KIND_CREATE
#         assert notify["primary_key"] == str(primary_key)
#
#         # Propagate notification to worker.
#         await main.send_input(notify)
#
#         # Check that observer evaluation was requested.
#         notify = await channel_layer.receive(CHANNEL_WORKER)
#         assert notify["type"] == TYPE_EVALUATE
#         assert notify["observer"] == observer_id
#
#         # Propagate notification to worker.
#         await worker.send_input(notify)
#         response = await client.receive_json_from()
#         assert response["msg"] == "added"
#         assert response["primary_key"] == "id"
#         assert response["order"] == 0
#         assert response["item"] == {
#             "id": primary_key,
#             "enabled": True,
#             "name": "hello world",
#         }
#
#     # No other messages should be sent.
#     assert await client.receive_nothing() is True
#     await client.disconnect()
#
#     # Ensure that subscriber has been removed.
#     await assert_subscribers(0)
#
#     async with async_timeout.timeout(1):
#         # Run observer again and it should skip evaluation because there are no more subscribers.
#         await worker.send_input({"type": TYPE_EVALUATE, "observer": observer_id})
#
#     assert await worker.receive_nothing() is True
