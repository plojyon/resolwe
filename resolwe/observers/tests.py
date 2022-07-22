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
from resolwe.permissions.models import PermissionGroup, PermissionModel, Permission

from .consumers import ClientConsumer
from .models import Observer
from .protocol import (
    CHANGE_TYPE_CREATE,
    CHANGE_TYPE_DELETE,
    CHANGE_TYPE_UPDATE,
    GROUP_SESSIONS,
    TYPE_ITEM_UPDATE,
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
            username="bob",
            email="user@test.com",
            first_name="Bob",
            last_name="Bobnik",
        )
        self.impostor = get_user_model().objects.create(
            username="capital-bob",
            email="bob@bob.bob",
            first_name="Capital",
            last_name="Bobnik",
        )
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
        """Assert a signal is queued in a channel and send it to the client."""
        # Check that a signal was generated.
        channel_layer = get_channel_layer()
        async with async_timeout.timeout(1):
            notify = await channel_layer.receive(channel)

        self.assertDictEqual(notify, signal)

        # Propagate notification to worker.
        await client.send_input(notify)

    async def assert_empty_channel(self, channel):
        """Assert there are no messages queued in a given channel."""
        channel_layer = get_channel_layer()
        with self.assertRaises(asyncio.exceptions.TimeoutError):
            async with async_timeout.timeout(0.01):
                await channel_layer.receive(channel)

    async def await_subscription_count(self, count):
        """Wait until the number of all subscriptions is equal to count."""

        @database_sync_to_async
        def get_subscription_count():
            return Observer.objects.filter(session_id="session_28946").count()

        async with async_timeout.timeout(1):
            while await get_subscription_count() != count:
                await asyncio.sleep(0.01)

    async def atest_ws_subscribe_unsubscribe(self):
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

        await self.await_subscription_count(0)

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
        await client.send_to(
            text_data=json.dumps(
                {
                    "action": "subscribe",
                    "table": Data._meta.db_table,
                    "type_of_change": "DELETE",
                    "primary_key": 42,
                }
            )
        )
        # We have to wait for the subscriptions to register
        await self.await_subscription_count(3)

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

        print("creating data")
        data = await create_data()
        print("created data")

        print("list received signals:")
        # print all messages in channel
        channel_layer = get_channel_layer()
        while True:
            try:
                async with async_timeout.timeout(0.01):
                    print(await channel_layer.receive(channel))
            except asyncio.exceptions.TimeoutError:
                break

        return await client.disconnect()
        ###################################################################

        # TODO: update, then create?
        await propagate_data_signal(CHANGE_TYPE_CREATE)
        await propagate_data_signal(CHANGE_TYPE_UPDATE)

        packet = json.loads(await client.receive_from())
        self.assertEquals(packet["table"], "flow_data")
        self.assertEquals(packet["primary_key"], "42")
        self.assertEquals(packet["type_of_change"], "CREATE")

        packet = json.loads(await client.receive_from())
        self.assertEquals(packet["table"], "flow_data")
        self.assertEquals(packet["primary_key"], "42")
        self.assertEquals(packet["type_of_change"], "UPDATE")

        data.name = "name2"
        await database_sync_to_async(data.save)()
        await propagate_data_signal(CHANGE_TYPE_UPDATE)
        packet = json.loads(await client.receive_from())
        self.assertEquals(packet["table"], "flow_data")
        self.assertEquals(packet["primary_key"], "42")
        self.assertEquals(packet["type_of_change"], "UPDATE")

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
        await self.await_subscription_count(2)

        data.name = "name2"
        await database_sync_to_async(data.save)()
        await self.assert_empty_channel(channel)

        await database_sync_to_async(data.delete)()
        await propagate_data_signal(CHANGE_TYPE_DELETE)
        packet = json.loads(await client.receive_from())
        self.assertEquals(packet["table"], "flow_data")
        self.assertEquals(packet["primary_key"], "42")
        self.assertEquals(packet["type_of_change"], "DELETE")

        # the observers should be deleted after the resource
        await self.await_subscription_count(0)

        await client.disconnect()

    async def atest_remove_observers_after_socket_close(self):
        client = WebsocketCommunicator(self.client_consumer, "/ws/session_28946")
        client.scope["user"] = self.user
        connected, _ = await client.connect()
        self.assertTrue(connected)

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
        await self.await_subscription_count(1)
        await client.disconnect()
        await self.await_subscription_count(0)

    async def test_table_watching(self):
        # Create a subscription to the Data table.
        @database_sync_to_async
        def subscribe():
            Observer.objects.create(
                table=Data._meta.db_table,
                resource_pk=None,
                change_type=CHANGE_TYPE_CREATE,
                session_id="session_28946",
                user=self.user,
            )
            Observer.objects.create(
                table=Data._meta.db_table,
                resource_pk=None,
                change_type=CHANGE_TYPE_DELETE,
                session_id="session_28946",
                user=self.user,
            )

        await subscribe()
        await self.await_subscription_count(2)

        # Create a new Data object
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

        data = await create_data()

        # Assert we detect creations.
        message = {
            "type": TYPE_ITEM_UPDATE,
            "table": Data._meta.db_table,
            "type_of_change": CHANGE_TYPE_CREATE,
            "primary_key": "42",
            "app_label": Data._meta.app_label,
            "model_name": Data._meta.object_name,
        }

        channel = GROUP_SESSIONS.format(session_id="session_28946")
        async with async_timeout.timeout(1):
            notify = await get_channel_layer().receive(channel)
        self.assertDictEqual(notify, message)

        await self.assert_empty_channel(channel)

        # Delete the Data object
        @database_sync_to_async
        def delete_data(data):
            data.delete()

        await delete_data(data)

        # Assert we detect deletions.
        message = {
            "type": TYPE_ITEM_UPDATE,
            "table": Data._meta.db_table,
            "type_of_change": CHANGE_TYPE_DELETE,
            "primary_key": "42",
            "app_label": Data._meta.app_label,
            "model_name": Data._meta.object_name,
        }

        channel = GROUP_SESSIONS.format(session_id="session_28946")
        async with async_timeout.timeout(1):
            notify = await get_channel_layer().receive(channel)
        self.assertDictEqual(notify, message)

        await self.assert_empty_channel(channel)

        # Assert subscription didn't delete because Data got deleted.
        await self.await_subscription_count(2)

    async def atest_change_permission_group(self):

        # Create a Data object visible to self.impostor.
        @database_sync_to_async
        def create_data():
            data = Data.objects.create(
                pk=42,
                name="Public data",
                slug="public-data",
                contributor=self.user,
                process=self.process,
                size=0,
            )
            data.set_permission(Permission.VIEW, self.impostor)
            return data

        data = await create_data()

        # Create a subscription to the Data object by self.impostor.
        @database_sync_to_async
        def subscribe():
            Observer.objects.create(
                table=Data._meta.db_table,
                resource_pk=42,
                change_type=CHANGE_TYPE_UPDATE,
                session_id="session_28946",
                user=self.impostor,
            )
            Observer.objects.create(
                table=Data._meta.db_table,
                resource_pk=42,
                change_type=CHANGE_TYPE_DELETE,
                session_id="session_28946",
                user=self.impostor,
            )

        await subscribe()

        # Reset the PermissionGroup of the Data object
        # (removes permissions to self.impostor)
        @database_sync_to_async
        def change_permission_group(data):
            data.permission_group = PermissionGroup.objects.create()
            data.save()

        await change_permission_group(data)

        # Assert that self.impostor sees this as a deletion.
        message = {
            "type": TYPE_ITEM_UPDATE,
            "table": Data._meta.db_table,
            "type_of_change": CHANGE_TYPE_DELETE,
            "primary_key": "42",
            "app_label": Data._meta.app_label,
            "model_name": Data._meta.object_name,
        }

        channel = GROUP_SESSIONS.format(session_id="session_28946")
        async with async_timeout.timeout(1):
            notify = await get_channel_layer().receive(channel)
        self.assertDictEqual(notify, message)

        await self.assert_empty_channel(channel)

        # Assert self.impostor is no longer subscribed to changes
        await self.await_subscription_count(0)

    async def atest_change_permission_value(self):
        pass

    async def atest_change_permission_model(self):
        pass

    async def test_gain_permissions(self):
        # Create a new Data object
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

        data = await create_data()

        # Create a subscription to the Data table by self.impostor.
        @database_sync_to_async
        def subscribe():
            Observer.objects.create(
                table=Data._meta.db_table,
                resource_pk=None,
                change_type=CHANGE_TYPE_CREATE,
                session_id="session_28946",
                user=self.impostor,
            )
            Observer.objects.create(
                table=Data._meta.db_table,
                resource_pk=None,
                change_type=CHANGE_TYPE_UPDATE,
                session_id="session_28946",
                user=self.impostor,
            )
            Observer.objects.create(
                table=Data._meta.db_table,
                resource_pk=None,
                change_type=CHANGE_TYPE_DELETE,
                session_id="session_28946",
                user=self.impostor,
            )

        await subscribe()
        await self.await_subscription_count(3)

        # Grant self.impostor view permissions to the Data object.
        @database_sync_to_async
        def grant_permissions(data):
            data.set_permission(Permission.VIEW, self.impostor)

        await grant_permissions(data)

        # Assert we detect gaining permissions as creations.
        message = {
            "type": TYPE_ITEM_UPDATE,
            "table": Data._meta.db_table,
            "type_of_change": CHANGE_TYPE_CREATE,
            "primary_key": "42",
            "app_label": Data._meta.app_label,
            "model_name": Data._meta.object_name,
        }

        channel = GROUP_SESSIONS.format(session_id="session_28946")
        async with async_timeout.timeout(1):
            notify = await get_channel_layer().receive(channel)
        self.assertDictEqual(notify, message)

        await self.assert_empty_channel(channel)

    # TODO: simple
    # async def test_observe_table(self):
    # TODO: make/modify/delete obj with(out) permissions on an observed table
    # async def test_double_subscription(self):
    # async def test_subscribe_to_forbidden_object(self):
    # TODO: assert subscription fails
    # async def test_subscribe_to_nonexistent_object(self):
    # TODO: assert subscription fails

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
