import asyncio
from contextlib import nullcontext as does_not_raise
import os
import socket
from typing import Iterator
import pytest
from aiosdnotify import SystemdNotifier


@pytest.fixture
def watchdog_socket() -> Iterator[socket.socket]:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.bind('\0' + 'watchdog')
    os.environ['NOTIFY_SOCKET'] = '@watchdog'
    os.environ['WATCHDOG_USEC'] = '1000000'
    yield sock
    sock.close()
    del os.environ['NOTIFY_SOCKET']
    del os.environ['WATCHDOG_USEC']


@pytest.mark.asyncio
async def test_no_exceptions_without_environment() -> None:
    with does_not_raise():
        async with SystemdNotifier() as notifier:
            notifier.ready()
            notifier.status("Testing")


@pytest.mark.asyncio
async def test_connect_throws_exception_when_debug() -> None:
    with pytest.raises(EnvironmentError):
        await SystemdNotifier(debug=True).connect()


def test_status_throws_exception_when_debug() -> None:
    with pytest.raises(RuntimeError):
        SystemdNotifier(debug=True).status("Testing")


def test_start_watchdog_throws_exception_when_debug() -> None:
    with pytest.raises(EnvironmentError):
        SystemdNotifier(debug=True).start_watchdog()


@pytest.mark.asyncio
async def test_sends_notifications(watchdog_socket: socket.socket) -> None:
    async with SystemdNotifier() as notifier:
        notifier.ready()
        ready = watchdog_socket.recv(1024)
        assert ready == b"READY=1"
        notifier.status("Testing")
        status = watchdog_socket.recv(1024)
        assert status == b"STATUS=Testing"
        await asyncio.sleep(1)
        data = watchdog_socket.recv(1024)
        assert data == b"WATCHDOG=1"
