"""
Originally bridged Notification.objects.create(...) calls to the
WebSocket layer via post_save. That signal only fires for ORM writes,
so once views.py moved to raw SQL inserts (see create_notification() /
_push_notification_over_websocket() in views.py), this receiver stopped
being reached from anywhere in the app — it's kept only as a safety net
in case something outside this codebase (Django admin, a shell script)
still calls Notification.objects.create() directly.

If no ASGI server / channel layer is running (e.g. under plain
`manage.py runserver`, which is HTTP-only), group_send() below is a
no-op against the in-memory layer with nothing listening — it does
NOT raise, so this signal is always safe to leave connected even in
plain-HTTP dev mode.
"""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Notification


@receiver(post_save, sender=Notification)
def push_notification_over_websocket(sender, instance, created, **kwargs):

    if not created:
        return

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    async_to_sync(channel_layer.group_send)(
        f"notifications_{instance.user_id}",
        {
            "type": "notification.message",
            "payload": {
                "id": instance.id,
                "type": instance.type,
                "message": instance.message,
                "is_read": instance.read_status,
                "created_at": instance.timestamp.isoformat(),
            },
        },
    )
