"""Consumers for Observers."""

from channels.generic.websocket import JsonWebsocketConsumer

from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache

from .models import Observer, Subscription
from .protocol import (
    CHANGE_TYPE_DELETE,
    GROUP_SESSIONS,
    THROTTLE_SEMAPHORE_DELAY,
    THROTTLE_SEMAPHORE_EVALUATE,
    THROTTLE_SEMAPHORE_IGNORE,
    throttle_cache_key,
)
from .settings import get_observer_settings


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


def throttle_semaphore(observer_id):
    """Check if observer should be evaluated, delayed or ignored.

    Increase the observer counter if throttle cache exists.
    """
    cache_key = throttle_cache_key(observer_id)
    throttle_rate = get_observer_settings()["throttle_rate"]

    try:
        count = cache.incr(cache_key)
        # Ignore if delayed observer already scheduled.
        return THROTTLE_SEMAPHORE_DELAY if count == 2 else THROTTLE_SEMAPHORE_IGNORE
    except ValueError:
        count = cache.get_or_set(cache_key, default=1, timeout=throttle_rate)
        # Ignore if cache was set and increased in another thread.
        return THROTTLE_SEMAPHORE_EVALUATE if count == 1 else THROTTLE_SEMAPHORE_IGNORE

    assert False  # This should never happen.
