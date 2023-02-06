import asyncio
from contextlib import suppress
from django.conf import settings

from ..auth import get_user
from ..generic.websocket import AsyncWebsocketConsumer, AsyncJsonWebsocketConsumer


class SessionCheckAsyncWebsocketConsumer(AsyncWebsocketConsumer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.check_task = None

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            # cleanup check
            if self.check_task is not None:
                self.check_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self.check_task

    async def check_session(self):
        """
        Gets user from scope and check it is not anonymous
        """
        user = await get_user(self.scope)
        if user.is_anonymous:
            await self.close()
        return user

    async def _run_session_check(self, interval):
        while True:
            await asyncio.sleep(interval)
            await self.check_session()

    async def accept(self, subprotocol=None):
        """
        Accepts an incoming socket and create check task
        """
        await super().accept(subprotocol)
        self.check_task = asyncio.create_task(
            self._run_session_check(
                interval=getattr(
                    settings,
                    'CHANNELS_WS_SESSION_CHECK_INTERVAL',
                    120
                )
            )
        )


class AsyncJsonSessionCheckWebsocketConsumer(SessionCheckAsyncWebsocketConsumer, AsyncJsonWebsocketConsumer):
    pass
