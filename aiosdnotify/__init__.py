import socket
import asyncio
import os
import logging


__version__ = "1.0.0"

logger = logging.getLogger(__name__)


class SystemdNotifier:
    """This class holds a connection to the systemd notification socket
    and can be used to send messages to systemd using its notify method."""

    def __init__(self, debug=False, warn_limit=3, watchdog=True):
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

        The default watchdog=True enrolls SystemdNotifier in the watchdog protocol
        for a unit service
        """
        self.debug = debug
        self.warn_limit = warn_limit
        self.watchdog = watchdog
        self._warnings = 0
        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: asyncio.DatagramProtocol | None = None
        self._watchdog_task: asyncio.Task | None = None
        self._ready_event = asyncio.Event()

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

    def disconnect(self):
        if self._transport is not None and not self._transport.is_closing():
            self._transport.close()

    def _notify(self, state_str: str):
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

    def ready(self):
        self._notify("READY=1")
        self._ready_event.set()

    def status(self, status: str):
        self._notify(f"STATUS={status}")

    def start_watchdog(self, interval: float | None = None):
        if interval is None:
            interval_microseconds = float(os.getenv('WATCHDOG_USEC'))
            if interval_microseconds is None:
                raise EnvironmentError('Unable to determine watchdog interval from ENV, and none was specified')
            interval = interval_microseconds / 1_000_000 / 2  # We try to notify at half the env specified interval
        self._watchdog_task = asyncio.create_task(
            self._watchdog(interval))

    async def _watchdog(self, interval: float):
        await self._ready_event.wait()
        while True:
            self._notify('WATCHDOG=1')
            await asyncio.sleep(interval)

    async def __aenter__(self):
        await self.connect()
        if self.watchdog:
            self.start_watchdog()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if (
                self._watchdog_task
                and not self._watchdog_task.done()
                and not self._watchdog_task.cancelled()
        ):
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
        self.disconnect()
