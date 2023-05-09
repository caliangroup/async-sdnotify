import socket
import asyncio
import os
import logging

from typing import Callable


__version__ = "0.3.2"

logger = logging.getLogger(__name__)


class SystemdNotifier:
    """This class holds a connection to the systemd notification socket
    and can be used to send messages to systemd using its notify method."""

    def __init__(self, debug=False, warn_limit=3):
        """Instantiate a new notifier object. This will initiate a connection
        to the systemd notification socket.

        Normally this method silently ignores exceptions (for example, if the
        systemd notification socket is not available) to allow applications to
        function on non-systemd based systems. However, setting debug=True will
        cause this method to raise any exceptions generated to the caller, to
        aid in debugging.

        If SystemdNotifier is not configured to raise Exceptions, it will emit
        warnings. Use warn_limit to govern how many warnings in a row can be
        emitted. This behavior can be deactivated by setting warn_limit=0.
        """
        self.debug = debug
        self.warn_limit = warn_limit
        self._warnings = 0
        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: asyncio.DatagramProtocol | None = None
        self._regular_notification_task: asyncio.Task | None = None

    async def connect(self):
        try:
            notify_socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            addr = os.getenv('NOTIFY_SOCKET')
            if addr[0] == '@':
                addr = '\0' + addr[1:]
            notify_socket.connect(addr)
            self._transport, self._protocol = await asyncio.get_running_loop().create_datagram_endpoint(
                asyncio.DatagramProtocol, sock=notify_socket)
        except Exception as e:
            if self.debug:
                raise
            elif self.warn_limit:
                logger.warning('SystemdNotifier failed to connect', exc_info=True)

    def notify(self, state_str: str):
        """Send a notification to systemd. state is a string; see
        the man page of sd_notify (http://www.freedesktop.org/software/systemd/man/sd_notify.html)
        for a description of the allowable values.

        Normally this method silently ignores exceptions (for example, if the
        systemd notification socket is not available) to allow applications to
        function on non-systemd based systems. However, setting debug=True will
        cause this method to raise any exceptions generated to the caller, to
        aid in debugging."""
        try:
            self._transport.sendto(state_str.encode())
            self._warnings = 0
        except Exception:
            if self.debug:
                raise
            elif self._warnings < self.warn_limit:
                logger.warning('SystemdNotifier failed to notify', exc_info=True)
                self._warnings += 1

    def disconnect(self):
        if self._transport is not None and not self._transport.is_closing():
            self._transport.close()

    def notify_regularly(
            self,
            interval: float | None = None,
            state_message: str | None = None,
            state_callback: Callable[[], str] | None = None
    ):
        if interval is None:
            interval_microseconds = float(os.getenv('WATCHDOG_USEC'))
            if interval_microseconds is None:
                raise EnvironmentError('Unable to determine watchdog inteval from ENV, and none was specified')
            interval = interval_microseconds / 1000
        self._regular_notification_task = asyncio.create_task(
            self._notify_regularly(interval, state_message, state_callback))

    async def _notify_regularly(
            self,
            interval: float,
            state_message: str | None,
            state_callback: Callable[[], bytes] | None
    ):
        while True:
            if state_callback:
                state_message = state_callback()
            elif state_message is None:
                state_message = ''
            self.notify(state_message)
            await asyncio.sleep(interval)

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if (
                self._regular_notification_task
                and not self._regular_notification_task.done()
                and not self._regular_notification_task.cancelled()
        ):
            self._regular_notification_task.cancel()
            try:
                await self._regular_notification_task
            except asyncio.CancelledError:
                pass
        self.disconnect()
