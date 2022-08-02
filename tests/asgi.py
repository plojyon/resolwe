from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path
from resolwe.observers.consumers import ClientConsumer
from django.conf.urls import url

application = ProtocolTypeRouter(
    {
        "websocket": URLRouter(
            [url(r"^ws/(?P<session_id>.+)$", ClientConsumer.as_asgi())]
        ),
    }
)
