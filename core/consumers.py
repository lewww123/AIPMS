import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add("notifications", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("notifications", self.channel_name)

    # This name MUST match the 'type' in your shell script
    async def send_notification(self, event):
        # We send the message back to the browser via WebSocket
        await self.send(text_data=json.dumps({
            'message': event['message'],
            'type': event.get('alert_type', 'blue') # Relaying the alert style
        }))