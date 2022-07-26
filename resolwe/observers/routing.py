"""Routing rules for websocket connections."""
from channels.routing import ChannelNameRouter, ProtocolTypeRouter, URLRouter

from django.urls import path

from .consumers import ClientConsumer, MainConsumer, WorkerConsumer
from .protocol import CHANNEL_WORKER
from .views import QueryObserverSubscribeView, QueryObserverUnsubscribeView

application = ProtocolTypeRouter(
    {
        # Client-facing WebSocket Consumers.
        "websocket": URLRouter(
            [path("ws/<slug:session_id>", ClientConsumer.as_asgi())]
        ),
    }
)
