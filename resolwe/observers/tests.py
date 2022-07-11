"""Tests for observers."""
import asyncio

import async_timeout
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import ApplicationCommunicator, WebsocketCommunicator
from django.urls import path
from resolwe.flow.models import Data, Process, DescriptorSchema
from resolwe.test import TestCase
from django.contrib.auth import get_user_model
from channels.auth import AuthMiddlewareStack
from rest_framework.test import force_authenticate

from .consumers import ClientConsumer, MainConsumer
from .protocol import CHANNEL_MAIN


class ObserverTestCase(TestCase):
    def setUp(self):
        super().setUp()

        self.process = Process.objects.create(
            name="Dummy process", contributor=self.contributor
        )

        self.descriptor_schema = DescriptorSchema.objects.create(
            name="Descriptor schema",
            contributor=self.contributor,
            schema=[
                {
                    "name": "test_field",
                    "type": "basic:string:",
                    "default": "default value",
                }
            ],
        )

        self.user = get_user_model().objects.create_user(
            username="xX-auth3nt1cat0r-Xx",
            email="user@test.com",
            first_name="John",
            last_name="Williams",
        )

    # @async_test
    async def test_auth(self):
        client_consumer = AuthMiddlewareStack(
            URLRouter([path("ws/<slug:subscriber_id>", ClientConsumer().as_asgi())])
        )
        client = WebsocketCommunicator(client_consumer, "/ws/test-session")
        # client = WSClient(client_consumer)
        client.force_login(self.user)

        connected, _ = await client.connect()
        self.assertTrue(connected)
        # self.assertEquals(client.instance.scope["user"], self.user)
        await client.disconnect()

    async def btest_bob(self):
        client_consumer = URLRouter(
            [path("ws/<slug:subscriber_id>", ClientConsumer().as_asgi())]
        )

        client = WebsocketCommunicator(client_consumer, "/ws/test-session")
        main = ApplicationCommunicator(
            MainConsumer(), {"type": "channel", "channel": CHANNEL_MAIN}
        )

        # Connect client.
        connected, _ = await client.connect()
        assert connected

        # Subscribe to updates.
        client.send_json(
            {
                "action": "subscribe",
                "table": Data._meta.db_table,
                "type_of_change": "UPDATE",
                "primary_key": 42,
            }
        )

        # Create a single model instance for the observer model.
        @database_sync_to_async
        def create_model():
            return Data.objects.create(
                name="Data object",
                contributor=self.contributor,
                process=self.process,
                # descriptor_schema=self.descriptor_schema,
            )

        data = await create_model()
        # TODO: assert existance of an observer, has 1 subscriber

        await client.disconnect()


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
