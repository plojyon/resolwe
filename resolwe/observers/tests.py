# pylint: disable=missing-docstring

import asyncio
import json

import async_timeout
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.urls import path

from rest_framework import status

from resolwe.flow.models import Data, Entity, Process
from resolwe.flow.views import DataViewSet
from resolwe.permissions.models import Permission, PermissionGroup
from resolwe.test import TransactionResolweAPITestCase

from .consumers import ClientConsumer
from .models import Observer
from .protocol import (
    CHANGE_TYPE_CREATE,
    CHANGE_TYPE_DELETE,
    CHANGE_TYPE_UPDATE,
    GROUP_SESSIONS,
    TYPE_ITEM_UPDATE,
)


class ObserverTestCase(TransactionTestCase):
    def setUp(self):
        super().setUp()

        self.user_alice = get_user_model().objects.create(
            username="alice",
            email="alice@test.com",
            first_name="Ana",
            last_name="Banana",
        )
        self.user_bob = get_user_model().objects.create(
            username="capital-bob",
            email="bob@bob.bob",
            first_name="Capital",
            last_name="Bobnik",
        )
        self.process = Process.objects.create(
            name="Dummy process", contributor=self.user_alice
        )

        self.client_consumer = URLRouter(
            [path("ws/<slug:session_id>", ClientConsumer().as_asgi())]
        )

    async def clear_channel(self, channel):
        """A hack to clear all uncaught messages from the channel layer."""
        channel_layer = get_channel_layer()
        while True:
            try:
                async with async_timeout.timeout(0.01):
                    await channel_layer.receive(channel)
            except asyncio.TimeoutError:
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
        with self.assertRaises(asyncio.TimeoutError):
            async with async_timeout.timeout(0.01):
                await channel_layer.receive(channel)

    async def await_subscription_count(self, count):
        """Wait until the number of all subscriptions is equal to count."""

        @database_sync_to_async
        def get_subscription_count():
            return Observer.objects.filter(session_id="test_session").count()

        async with async_timeout.timeout(1):
            while await get_subscription_count() != count:
                await asyncio.sleep(0.01)

    async def test_websocket_subscribe_unsubscribe(self):
        channel = GROUP_SESSIONS.format(session_id="test_session")
        await self.clear_channel(channel)

        client = WebsocketCommunicator(self.client_consumer, "/ws/test_session")
        connected, _ = await client.connect()
        self.assertTrue(connected)

        async def propagate_entity_signal(change):
            await self.assert_and_propagate_signal(
                {
                    "type": TYPE_ITEM_UPDATE,
                    "type_of_change": change,
                    "primary_key": "43",
                    "table": Entity._meta.db_table,
                    "app_label": Entity._meta.app_label,
                    "model_name": Entity._meta.object_name,
                },
                channel,
                client,
            )

        await self.await_subscription_count(0)

        # Subscribe to updates.
        @database_sync_to_async
        def subscribe():
            args = {
                "resource_pk": 43,
                "table": Entity._meta.db_table,
                "user": self.user_alice,
                "session_id": "test_session",
            }
            Observer.objects.create(change_type="CREATE", **args)
            Observer.objects.create(change_type="UPDATE", **args)
            Observer.objects.create(change_type="DELETE", **args)

        await subscribe()

        # Create an Entity object.
        @database_sync_to_async
        def create_entity():
            entity = Entity.objects.create(
                pk=43,
                name="Test entity",
                slug="test-entity",
                contributor=self.user_alice,
            )
            entity.set_permission(Permission.OWNER, self.user_alice)
            return entity

        entity = await create_entity()

        await propagate_entity_signal(CHANGE_TYPE_CREATE)
        packet = json.loads(await client.receive_from())
        self.assertEquals(packet["primary_key"], "43")
        self.assertEquals(packet["type_of_change"], "CREATE")

        entity.name = "name2"
        await database_sync_to_async(entity.save)()
        await propagate_entity_signal(CHANGE_TYPE_UPDATE)
        packet = json.loads(await client.receive_from())
        self.assertEquals(packet["primary_key"], "43")
        self.assertEquals(packet["type_of_change"], "UPDATE")

        # Unsubscribe from updates.
        @database_sync_to_async
        def unsubscribe():
            Observer.objects.filter(resource_pk=43, change_type="UPDATE").delete()

        await unsubscribe()
        await self.await_subscription_count(2)

        entity.name = "name2"
        await database_sync_to_async(entity.save)()
        await self.assert_empty_channel(channel)

        await database_sync_to_async(entity.delete)()
        await propagate_entity_signal(CHANGE_TYPE_DELETE)
        packet = json.loads(await client.receive_from())
        self.assertEquals(packet["primary_key"], "43")
        self.assertEquals(packet["type_of_change"], "DELETE")

        # The observers should be deleted after the resource.
        await self.await_subscription_count(0)

        await client.disconnect()

    async def test_remove_observers_after_socket_close(self):
        client = WebsocketCommunicator(self.client_consumer, "/ws/test_session")
        client.scope["user"] = self.user_alice
        connected, _ = await client.connect()
        self.assertTrue(connected)

        @database_sync_to_async
        def subscribe():
            Observer.objects.create(
                table=Data._meta.db_table,
                change_type="UPDATE",
                resource_pk=42,
                user=self.user_alice,
                session_id="test_session",
            )

        await subscribe()
        await self.await_subscription_count(1)
        await client.disconnect()
        await self.await_subscription_count(0)

    async def test_observe_table(self):
        channel = GROUP_SESSIONS.format(session_id="test_session")

        # Create a subscription to the Data table.
        @database_sync_to_async
        def subscribe():
            Observer.objects.create(
                table=Data._meta.db_table,
                resource_pk=None,
                change_type=CHANGE_TYPE_CREATE,
                session_id="test_session",
                user=self.user_alice,
            )
            Observer.objects.create(
                table=Data._meta.db_table,
                resource_pk=None,
                change_type=CHANGE_TYPE_DELETE,
                session_id="test_session",
                user=self.user_alice,
            )

        await subscribe()
        await self.await_subscription_count(2)

        # Create a new Data object.
        @database_sync_to_async
        def create_data():
            return Data.objects.create(
                pk=42,
                name="Test data",
                slug="test-data",
                contributor=self.user_alice,
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

        async with async_timeout.timeout(1):
            notify = await get_channel_layer().receive(channel)
        self.assertDictEqual(notify, message)

        await self.assert_empty_channel(channel)

        # Assert subscription didn't delete because Data got deleted.
        await self.await_subscription_count(2)

    async def test_change_permission_group(self):
        client = WebsocketCommunicator(self.client_consumer, "/ws/test-session")
        connected, details = await client.connect()
        self.assertTrue(connected)

        # Create a Data object visible to Bob.
        @database_sync_to_async
        def create_data():
            data = Data.objects.create(
                pk=42,
                name="Test data",
                slug="test-data",
                contributor=self.user_alice,
                process=self.process,
                size=0,
            )
            data.set_permission(Permission.VIEW, self.user_bob)
            return data

        data = await create_data()

        # Create a subscription to the Data object by Bob.
        @database_sync_to_async
        def subscribe():
            Observer.objects.create(
                table=Data._meta.db_table,
                resource_pk=42,
                change_type=CHANGE_TYPE_UPDATE,
                session_id="test_session",
                user=self.user_bob,
            )
            Observer.objects.create(
                table=Data._meta.db_table,
                resource_pk=42,
                change_type=CHANGE_TYPE_DELETE,
                session_id="test_session",
                user=self.user_bob,
            )

        await subscribe()

        # Reset the PermissionGroup of the Data object
        # (removes permissions to Bob)
        @database_sync_to_async
        def change_permission_group(data):
            data.permission_group = PermissionGroup.objects.create()
            data.save()

        await change_permission_group(data)

        # Assert that Bob sees this as a deletion.
        message = {
            "type": TYPE_ITEM_UPDATE,
            "table": Data._meta.db_table,
            "type_of_change": CHANGE_TYPE_DELETE,
            "primary_key": "42",
            "app_label": Data._meta.app_label,
            "model_name": Data._meta.object_name,
        }

        channel = GROUP_SESSIONS.format(session_id="test_session")
        async with async_timeout.timeout(1):
            notify = await get_channel_layer().receive(channel)
        self.assertDictEqual(notify, message)

        await self.assert_empty_channel(channel)

    async def test_modify_permissions(self):
        # Create a new Data object.
        @database_sync_to_async
        def create_data():
            return Data.objects.create(
                pk=42,
                name="Test data",
                slug="test-data",
                contributor=self.user_alice,
                process=self.process,
                size=0,
            )

        data = await create_data()

        # Create a subscription to the Data table by Bob.
        @database_sync_to_async
        def subscribe():
            Observer.objects.create(
                table=Data._meta.db_table,
                resource_pk=None,
                change_type=CHANGE_TYPE_CREATE,
                session_id="test_session",
                user=self.user_bob,
            )
            Observer.objects.create(
                table=Data._meta.db_table,
                resource_pk=None,
                change_type=CHANGE_TYPE_UPDATE,
                session_id="test_session",
                user=self.user_bob,
            )
            Observer.objects.create(
                table=Data._meta.db_table,
                resource_pk=None,
                change_type=CHANGE_TYPE_DELETE,
                session_id="test_session",
                user=self.user_bob,
            )

        await subscribe()
        await self.await_subscription_count(3)

        # Grant Bob view permissions to the Data object.
        @database_sync_to_async
        def grant_permissions(data):
            data.set_permission(Permission.VIEW, self.user_bob)

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

        channel = GROUP_SESSIONS.format(session_id="test_session")
        async with async_timeout.timeout(1):
            notify = await get_channel_layer().receive(channel)
        self.assertDictEqual(notify, message)

        await self.assert_empty_channel(channel)

        # Revoke permissions for Bob.
        @database_sync_to_async
        def revoke_permissions(data):
            data.set_permission(Permission.NONE, self.user_bob)

        await revoke_permissions(data)

        # Assert we detect losing permissions as deletions.
        message = {
            "type": TYPE_ITEM_UPDATE,
            "table": Data._meta.db_table,
            "type_of_change": CHANGE_TYPE_DELETE,
            "primary_key": "42",
            "app_label": Data._meta.app_label,
            "model_name": Data._meta.object_name,
        }

        channel = GROUP_SESSIONS.format(session_id="test_session")
        async with async_timeout.timeout(1):
            notify = await get_channel_layer().receive(channel)
        self.assertDictEqual(notify, message)

        await self.assert_empty_channel(channel)

    async def test_observe_table_no_permissions(self):
        # Create a subscription to the Data table by Bob.
        @database_sync_to_async
        def subscribe():
            Observer.objects.create(
                table=Data._meta.db_table,
                resource_pk=None,
                change_type=CHANGE_TYPE_CREATE,
                session_id="test_session",
                user=self.user_bob,
            )
            Observer.objects.create(
                table=Data._meta.db_table,
                resource_pk=None,
                change_type=CHANGE_TYPE_UPDATE,
                session_id="test_session",
                user=self.user_bob,
            )
            Observer.objects.create(
                table=Data._meta.db_table,
                resource_pk=None,
                change_type=CHANGE_TYPE_DELETE,
                session_id="test_session",
                user=self.user_bob,
            )

        await subscribe()
        await self.await_subscription_count(3)

        # Create a new Data object.
        @database_sync_to_async
        def create_data():
            data = Data.objects.create(
                pk=42,
                name="Test data",
                slug="test-data",
                contributor=self.user_alice,
                process=self.process,
                size=0,
            )
            return data

        data = await create_data()

        # Assert we don't detect creations (Bob doesn't have permissions).
        channel = GROUP_SESSIONS.format(session_id="test_session")
        await self.assert_empty_channel(channel)

        # Delete the Data object.
        @database_sync_to_async
        def delete_data(data):
            data.delete()

        await delete_data(data)

        # Assert we don't detect deletions.
        channel = GROUP_SESSIONS.format(session_id="test_session")
        await self.assert_empty_channel(channel)

        # Assert subscription didn't delete.
        await self.await_subscription_count(3)


class ObserverAPITestCase(TransactionResolweAPITestCase):
    def setUp(self):
        self.viewset = DataViewSet
        self.resource_name = "data-subscribe"
        super().setUp()
        self.list_view = self.viewset.as_view({"get": "subscribe_list"})
        self.detail_view = self.viewset.as_view({"get": "subscribe_detail"})

        user_model = get_user_model()
        self.user_alice = user_model.objects.create(
            username="alice",
            email="alice@test.com",
            first_name="Ana",
            last_name="Banana",
        )
        self.user_bob = user_model.objects.create(
            username="capital-bob",
            email="bob@bob.bob",
            first_name="Capital",
            last_name="Bobnik",
        )
        self.process = Process.objects.create(
            name="Dummy process", contributor=self.user_alice
        )
        Data.objects.create(
            pk=42,
            name="Test data",
            slug="test-data",
            contributor=self.user_alice,
            process=self.process,
            size=0,
        )
        self.client_consumer = URLRouter(
            [path("ws/<slug:subscriber_id>", ClientConsumer().as_asgi())]
        )

    def test_subscribe(self):
        # Subscribe to model updates.
        resp = self._get_list(user=self.user_alice, query_params={"session_id": "test"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(json.loads(resp.data)), 1)
        self.assertEqual(Observer.objects.count(), 1)
        self.assertEqual(
            Observer.objects.filter(
                change_type="CREATE",
                session_id="test",
                resource_pk=None,
                table="flow_data",
            ).count(),
            1,
        )

        # Subscribe to instance updates.
        resp = self._get_detail(
            42, user=self.user_alice, query_params={"session_id": "test"}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(json.loads(resp.data)), 2)
        self.assertEqual(Observer.objects.count(), 3)
        self.assertEqual(
            Observer.objects.filter(
                change_type="UPDATE",
                session_id="test",
                resource_pk=42,
                table="flow_data",
            ).count(),
            1,
        )
        self.assertEqual(
            Observer.objects.filter(
                change_type="DELETE",
                session_id="test",
                resource_pk=42,
                table="flow_data",
            ).count(),
            1,
        )

        # Re-subscribe to the same endpoint.
        resp = self._get_detail(
            42, user=self.user_alice, query_params={"session_id": "test"}
        )
        # Assert we don't have duplicate observers.
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Observer.objects.count(), 3)

    # def test_subscribe_no_auth(self):
    #     resp = self._get_detail(42, query_params={"session_id": "test"})
    #     # Data pk=42 isn't public, so we can't subscribe
    #     self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
    #     self.assertEqual(Observer.objects.count(), 0)
    #
    #     public_data = Data.objects.create(
    #         pk=31,
    #         name="Public data",
    #         slug="public-data",
    #         contributor=self.user_alice,
    #         process=self.process,
    #         size=0,
    #     )
    #     public_data.set_permission(Permission.VIEW, AnonymousUser())
    #
    #     resp = self._get_detail(31, query_params={"session_id": "test"})
    #     # Data pk=31 is public, so we can subscribe
    #     self.assertEqual(resp.status_code, status.HTTP_200_OK)
    #     self.assertEqual(Observer.objects.count(), 2)

    def test_subscribe_to_forbidden_object(self):
        resp = self._get_detail(
            42, user=self.user_bob, query_params={"session_id": "test"}
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Observer.objects.count(), 0)

    def test_subscribe_to_nonexistent_object(self):
        resp = self._get_detail(
            111, user=self.user_alice, query_params={"session_id": "test"}
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Observer.objects.count(), 0)
