# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------
import asyncio
import mock


class HangingAsyncMock(mock.AsyncMock):
    """Use this mock to hang on a awaitable coroutine.
    Useful for testing task cancellation.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.side_effect = self._do_hang
        self._is_hanging = asyncio.Event()
        self._stop_hanging = asyncio.Event()

    async def _do_hang(self, *args, **kwargs):
        self._is_hanging.set()
        await self._stop_hanging.wait()

    async def wait_for_hang(self):
        await self._is_hanging.wait()

    def is_hanging(self):
        return self._is_hanging.is_set()

    def stop_hanging(self):
        self._stop_hanging.set()
