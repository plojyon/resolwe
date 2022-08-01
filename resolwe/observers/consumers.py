"""Consumers for Observers."""

from channels.generic.websocket import JsonWebsocketConsumer

from django.contrib.contenttypes.models import ContentType

from .models import Observer, Subscription
from .protocol import CHANGE_TYPE_DELETE, GROUP_SESSIONS


class ClientConsumer(JsonWebsocketConsumer):
    """Consumer for client communication."""

    def websocket_connect(self, message):
        """Handle establishing a WebSocket connection."""
        session_id = self.scope["url_route"]["kwargs"]["session_id"]
        self.session_id = session_id

        # Accept the connection.
        super().websocket_connect(message)

    @property
    def groups(self):
        """Generate a list of groups this channel should add itself to."""
        if not hasattr(self, "session_id"):
            return []
        return [GROUP_SESSIONS.format(session_id=self.session_id)]

    def disconnect(self, code):
        """Handle closing the WebSocket connection."""
        Subscription.objects.filter(session_id=self.session_id).delete()
        self.close()

    def observers_item_update(self, msg):
        """Handle an item update signal."""
        content_type = ContentType.objects.get_for_id(msg["content_type_pk"])
        object_id = msg["object_id"]
        change_type = msg["change_type"]

        interested = Observer.get_interested(
            content_type=content_type, object_id=object_id, change_type=change_type
        )
        subscription_ids = map(
            lambda x: x.hex,
            list(
                Subscription.objects.filter(observers__in=interested)
                .values_list("subscription_id", flat=True)
                .distinct()
            ),
        )

        if change_type == CHANGE_TYPE_DELETE:
            # The observed object was either deleted or the user lost permissions.
            subscription = Subscription.objects.get(session_id=self.session_id)
            observers = Observer.objects.filter(
                content_type=content_type,
                object_id=object_id,
                # change_type = Any,
            )
            # Assure we don't stay subscribed to an illegal object.
            for observer in observers:
                subscription.observers.remove(observer)

        for subscription_id in subscription_ids:
            self.send_json(
                {
                    "subscription_id": subscription_id,
                    "object_id": object_id,
                    "change_type": change_type,
                }
            )
