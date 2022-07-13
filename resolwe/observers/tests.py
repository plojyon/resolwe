"""Tests for observers."""
import asyncio
import json

import async_timeout
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import ApplicationCommunicator, WebsocketCommunicator
from django.urls import path
from resolwe.flow.models import Data, Process, DescriptorSchema
from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from channels.auth import AuthMiddlewareStack
from rest_framework.test import force_authenticate

from .models import Subscriber, Observer
from .consumers import ClientConsumer, MainConsumer
from .protocol import CHANNEL_MAIN


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

        # self.descriptor_schema = DescriptorSchema.objects.create(
        #     name="Descriptor schema",
        #     contributor=self.contributor,
        #     schema=[
        #         {
        #             "name": "test_field",
        #             "type": "basic:string:",
        #             "default": "default value",
        #         }
        #     ],
        # )
        # self.descr

        self.client_consumer = URLRouter(
            [path("ws/<slug:subscriber_id>", ClientConsumer().as_asgi())]
        )

    async def test_ws_no_auth(self):
        client = WebsocketCommunicator(self.client_consumer, "/ws/test-session")

        connected, details = await client.connect()
        self.assertFalse(connected)
        self.assertEquals(details, 3000)  # code 3000 - unauthorized

        await client.disconnect()

    async def test_ws_auth(self):
        client = WebsocketCommunicator(self.client_consumer, "/ws/test-session-2")
        client.scope["user"] = self.user

        connected, _ = await client.connect()
        self.assertTrue(connected)

        await client.disconnect()

    async def test_ws_subscribe_unsubscribe(self):
        client = WebsocketCommunicator(self.client_consumer, "/ws/session_28946")
        client.scope["user"] = self.user
        connected, _ = await client.connect()
        self.assertTrue(connected)

        @database_sync_to_async
        def assertSubscriptionCount(count):
            print(list(Subscriber.objects.all()))
            sub = Subscriber.objects.get(session_id="session_28946")
            self.assertEquals(sub.observers.count(), count)

        await assertSubscriptionCount(0)

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
        await assertSubscriptionCount(1)

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
        await assertSubscriptionCount(0)

        await client.disconnect()

    async def test_notifications(self):
        return

        # Create a single model instance.
        @database_sync_to_async
        def create_model():
            return Data.objects.create(
                name="Data object",
                contributor=self.user,
                process=self.process,
                # descriptor_schema=self.descriptor_schema,
            )

        data = await create_model()
        # TODO: assert existance of an observer, has 1 subscriber


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
