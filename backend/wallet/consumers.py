"""
Real-time notification delivery over WebSocket.

Each connected user joins a per-user Channels group
("notifications_<user_id>"). Whenever a Notification row is created
anywhere in the codebase (Send, KYC approval, fraud flag, price
alert, ...), the post_save signal in wallet/signals.py pushes it
into that user's group, and this consumer forwards it down the
socket as JSON. If the user isn't currently connected, nothing is
lost — the Notification row is already sitting in the database and
NotificationListView will show it next time they load a page.

Frontend connects to:  ws://<host>/ws/notifications/?token=<JWT access token>
(see js/notifications.js)
"""

import json

from channels.generic.websocket import AsyncWebsocketConsumer


class NotificationConsumer(AsyncWebsocketConsumer):

    async def connect(self):

        user = self.scope.get("user")

        if user is None or not getattr(user, "is_authenticated", False):
            await self.close(code=4001)
            return

        self.group_name = f"notifications_{user.id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):

        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notification_message(self, event):
        """Handler name must match the `type` key sent via
        group_send() in wallet/signals.py (type "notification.message"
        -> method notification_message)."""

        await self.send(text_data=json.dumps(event["payload"]))
