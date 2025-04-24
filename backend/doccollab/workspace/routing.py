from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/document/', consumers.DocumentConsumer.as_asgi()),
]
