# pylint: disable=missing-docstring

import asyncio
import json

import async_timeout
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TransactionTestCase
from django.urls import path

from rest_framework import status

from resolwe.flow.models import Collection, Data, Entity, Process
from resolwe.flow.views import DataViewSet
from resolwe.permissions.models import Permission
from resolwe.test import TransactionResolweAPITestCase

from .consumers import ClientConsumer
from .models import Observer, Subscription
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
        """Clear all uncaught messages from the channel layer."""
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

    async def await_subscription_observer_count(self, count):
        """Wait until the number of all subscriptions is equal to count."""

        @database_sync_to_async
        def get_subscription_count():
            subs = Subscription.objects.filter(session_id="test_session")
            total = 0
            for sub in subs:
                total += sub.observers.count()
            return total

        try:
            async with async_timeout.timeout(1):
                while await get_subscription_count() != count:
                    await asyncio.sleep(0.01)
        except asyncio.TimeoutError:
            raise ValueError(
                "Expecting subscription-observer count to be {count}, but it's {actual}".format(
                    count=count, actual=await get_subscription_count()
                )
            )

    async def await_object_count(self, object, count):
        """Wait until the number of all observers is equal to count."""

        @database_sync_to_async
        def get_count():
            return object.objects.count()

        try:
            async with async_timeout.timeout(1):
                while await get_count() != count:
                    await asyncio.sleep(0.01)
        except asyncio.TimeoutError:
            raise ValueError(
                "Expecting {obj} count to be {count}, but it's {actual}".format(
                    obj=object.__name__, count=count, actual=await get_count()
                )
            )

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
                    "change_type": change,
                    "object_id": "43",
                    "content_type_pk": ContentType.objects.get_for_model(Entity).pk,
                },
                channel,
                client,
            )

        await self.await_subscription_observer_count(0)

        # Subscribe to C/D and U separately.
        @database_sync_to_async
        def subscribe():
            Subscription.objects.create(
                user=self.user_alice, session_id="test_session"
            ).subscribe(
                content_type=ContentType.objects.get_for_model(Entity),
                resource_ids=[43],
                change_types=["CREATE", "DELETE"],
            )
            Subscription.objects.create(
                user=self.user_alice, session_id="test_session"
            ).subscribe(
                content_type=ContentType.objects.get_for_model(Entity),
                resource_ids=[43],
                change_types=["UPDATE"],
            )

        await subscribe()

        await self.await_object_count(Subscription, 2)
        await self.await_object_count(Observer, 3)
        await self.await_subscription_observer_count(3)

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
        self.assertEquals(packet["object_id"], "43")
        self.assertEquals(packet["change_type"], "CREATE")

        entity.name = "name2"
        await database_sync_to_async(entity.save)()
        await propagate_entity_signal(CHANGE_TYPE_UPDATE)
        packet = json.loads(await client.receive_from())
        self.assertEquals(packet["object_id"], "43")
        self.assertEquals(packet["change_type"], "UPDATE")

        # Unsubscribe from updates.
        @database_sync_to_async
        def unsubscribe():
            Subscription.objects.get(
                observers__object_id=43, observers__change_type="UPDATE"
            ).delete()

        await unsubscribe()

        await self.await_object_count(Subscription, 1)
        # Update observer should be deleted because no one is subscribed to it.
        await self.await_object_count(Observer, 2)
        await self.await_subscription_observer_count(2)

        entity.name = "name2"
        await database_sync_to_async(entity.save)()
        await self.assert_empty_channel(channel)

        await database_sync_to_async(entity.delete)()
        await propagate_entity_signal(CHANGE_TYPE_DELETE)
        packet = json.loads(await client.receive_from())
        self.assertEquals(packet["object_id"], "43")
        self.assertEquals(packet["change_type"], "DELETE")

        await client.disconnect()

    async def test_remove_observers_after_socket_close(self):
        client = WebsocketCommunicator(self.client_consumer, "/ws/test_session")
        client.scope["user"] = self.user_alice
        connected, _ = await client.connect()
        self.assertTrue(connected)

        @database_sync_to_async
        def subscribe():
            Subscription.objects.create(
                user=self.user_alice, session_id="test_session"
            ).subscribe(
                content_type=ContentType.objects.get_for_model(Data),
                resource_ids=[42],
                change_types=["UPDATE"],
            )

        await subscribe()
        await self.await_subscription_observer_count(1)
        await client.disconnect()
        await self.await_subscription_observer_count(0)

    async def test_observe_content_type(self):
        channel = GROUP_SESSIONS.format(session_id="test_session")

        # Create a subscription to the Data content_type.
        @database_sync_to_async
        def subscribe():
            Subscription.objects.create(
                user=self.user_alice, session_id="test_session"
            ).subscribe(
                content_type=ContentType.objects.get_for_model(Data),
                resource_ids=[None],
                change_types=["CREATE", "DELETE"],
            )

        await subscribe()
        await self.await_subscription_observer_count(2)

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
            "content_type_pk": ContentType.objects.get_for_model(Data).pk,
            "change_type": CHANGE_TYPE_CREATE,
            "object_id": "42",
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
            "content_type_pk": ContentType.objects.get_for_model(Data).pk,
            "change_type": CHANGE_TYPE_DELETE,
            "object_id": "42",
        }

        async with async_timeout.timeout(1):
            notify = await get_channel_layer().receive(channel)
        self.assertDictEqual(notify, message)

        await self.assert_empty_channel(channel)

        # Assert subscription didn't delete because Data got deleted.
        await self.await_subscription_observer_count(2)

    async def test_change_permission_group(self):
        client = WebsocketCommunicator(self.client_consumer, "/ws/test-session")
        connected, details = await client.connect()
        self.assertTrue(connected)

        # Create a Data object visible to Bob.
        @database_sync_to_async
        def create_data():
            self.collection = Collection.objects.create(
                contributor=self.user_alice,
                name="Test collection",
            )
            self.collection.set_permission(Permission.VIEW, self.user_bob)

            self.collection2 = Collection.objects.create(
                contributor=self.user_alice,
                name="Test collection 2",
            )
            self.collection2.set_permission(Permission.NONE, self.user_bob)

            data = Data.objects.create(
                pk=42,
                name="Test data",
                slug="test-data",
                contributor=self.user_alice,
                process=self.process,
                collection=self.collection,
                size=0,
            )
            return data

        data = await create_data()

        # Create a subscription to the Data object by Bob.
        @database_sync_to_async
        def subscribe():
            Subscription.objects.create(
                user=self.user_bob, session_id="test_session"
            ).subscribe(
                content_type=ContentType.objects.get_for_model(Data),
                resource_ids=[42],
                change_types=["UPDATE", "DELETE"],
            )

        await subscribe()

        # Reset the PermissionGroup of the Data object
        # (removes permissions to Bob)
        @database_sync_to_async
        def change_permission_group(data):
            data.move_to_collection(self.collection2)
            # data.save()

        await change_permission_group(data)

        # Assert that Bob sees this as a deletion.
        message = {
            "type": TYPE_ITEM_UPDATE,
            "content_type_pk": ContentType.objects.get_for_model(Data).pk,
            "change_type": CHANGE_TYPE_DELETE,
            "object_id": "42",
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

        # Create a subscription to the Data content_type by Bob.
        @database_sync_to_async
        def subscribe():
            Subscription.objects.create(
                user=self.user_bob, session_id="test_session"
            ).subscribe(
                content_type=ContentType.objects.get_for_model(Data),
                resource_ids=[None],
                change_types=["CREATE", "UPDATE", "DELETE"],
            )

        await subscribe()
        await self.await_subscription_observer_count(3)

        # Grant Bob view permissions to the Data object.
        @database_sync_to_async
        def grant_permissions(data):
            data.set_permission(Permission.VIEW, self.user_bob)

        await grant_permissions(data)

        # Assert we detect gaining permissions as creations.
        message = {
            "type": TYPE_ITEM_UPDATE,
            "content_type_pk": ContentType.objects.get_for_model(Data).pk,
            "change_type": CHANGE_TYPE_CREATE,
            "object_id": "42",
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
            "content_type_pk": ContentType.objects.get_for_model(Data).pk,
            "change_type": CHANGE_TYPE_DELETE,
            "object_id": "42",
        }

        channel = GROUP_SESSIONS.format(session_id="test_session")
        async with async_timeout.timeout(1):
            notify = await get_channel_layer().receive(channel)
        self.assertDictEqual(notify, message)

        await self.assert_empty_channel(channel)

    async def test_observe_content_type_no_permissions(self):
        # Create a subscription to the Data content_type by Bob.
        @database_sync_to_async
        def subscribe():
            Subscription.objects.create(
                user=self.user_bob, session_id="test_session"
            ).subscribe(
                content_type=ContentType.objects.get_for_model(Data),
                resource_ids=[None],
                change_types=["CREATE", "UPDATE", "DELETE"],
            )

        await subscribe()
        await self.await_subscription_observer_count(3)

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
        await self.await_subscription_observer_count(3)


class ObserverAPITestCase(TransactionResolweAPITestCase):
    def setUp(self):
        self.viewset = DataViewSet
        self.resource_name = "data"
        super().setUp()
        self.list_view = self.viewset.as_view({"get": "subscribe"})
        # self.detail_view = self.viewset.as_view({"get": "subscribe_detail"})

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
        self.assertDictEqual(
            json.loads(resp.data),
            {"subscription_id": Subscription.objects.all()[0].subscription_id.hex},
        )
        self.assertEqual(Observer.objects.count(), 1)
        self.assertEqual(
            Observer.objects.filter(
                change_type="CREATE",
                object_id=None,
                content_type=ContentType.objects.get_for_model(Data),
            ).count(),
            1,
        )

        # Subscribe to instance updates.
        resp = self._get_list(
            user=self.user_alice, query_params={"session_id": "test", "ids": 42}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        sub_qs = Subscription.objects.filter(
            session_id="test", observers__object_id=42
        ).distinct()
        self.assertEqual(sub_qs.count(), 1)
        self.assertDictEqual(
            json.loads(resp.data),
            {"subscription_id": sub_qs.first().subscription_id.hex},
        )
        self.assertEqual(Observer.objects.count(), 3)
        self.assertEqual(
            Observer.objects.filter(
                change_type="UPDATE",
                object_id=42,
                content_type=ContentType.objects.get_for_model(Data),
            ).count(),
            1,
        )
        self.assertEqual(
            Observer.objects.filter(
                change_type="DELETE",
                object_id=42,
                content_type=ContentType.objects.get_for_model(Data),
            ).count(),
            1,
        )

        # Re-subscribe to the same endpoint.
        resp = self._get_list(
            user=self.user_alice, query_params={"session_id": "test", "ids": 42}
        )
        # Assert we don't have duplicate observers.
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Observer.objects.count(), 3)

    def test_subscribe_to_forbidden_object(self):
        resp = self._get_list(
            user=self.user_bob, query_params={"session_id": "test", "ids": 42}
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Observer.objects.count(), 0)

    def test_subscribe_to_nonexistent_object(self):
        resp = self._get_list(
            user=self.user_alice, query_params={"session_id": "test", "ids": 111}
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Observer.objects.count(), 0)
