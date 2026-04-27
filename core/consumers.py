import json
from channels.generic.websocket import AsyncWebsocketConsumer


class FarmUpdateConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add(
            "farm_updates",
            self.channel_name
        )
        await self.accept()
        print("WebSocket connected")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            "farm_updates",
            self.channel_name
        )

    async def send_notification(self, event):
        await self.send(text_data=json.dumps({
            "message": event["message"],
            "notification_type": event["notification_type"]
        }))