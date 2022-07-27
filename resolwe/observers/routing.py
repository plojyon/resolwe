from channels.routing import ChannelNameRouter, ProtocolTypeRouter, URLRouter
from django.urls import path

from .consumers import ClientConsumer, MainConsumer, WorkerConsumer
from .protocol import CHANNEL_MAIN, CHANNEL_WORKER
from .views import QueryObserverSubscribeView, QueryObserverUnsubscribeView

application = ProtocolTypeRouter(
    {
        # Subscription / unsubscription endpoint
        "http": URLRouter(
            [
                path("subscribe", QueryObserverSubscribeView.as_view()),
                path("unsubscribe", QueryObserverUnsubscribeView.as_view()),
            ]
        ),
        # Client-facing consumers.
        "websocket": URLRouter(
            [
                # To change the prefix, you can import ClientConsumer in your custom
                # Channels routing definitions instead of using these defaults.
                path("ws/<slug:subscriber_id>", ClientConsumer.as_asgi())
            ]
        ),
        # Background worker consumers.
        "channel": ChannelNameRouter(
            {
                CHANNEL_MAIN: MainConsumer.as_asgi(),
            }
        ),
    }
)
