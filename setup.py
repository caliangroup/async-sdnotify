from distutils.core import setup

VERSION = '0.3.2'

setup(
    name='sdnotify-asyncio',
    packages=['aiosdnotify'],
    version=VERSION,
    description='A pure Python implementation of systemd\'s service notification protocol (sd_notify)',
    author='Seat Snob / Brett Bethke',
    author_email='garrett@seatsnob.com',
    url='https://github.com/seatsnob/sdnotify-asyncio',
    keywords=['systemd'],
    long_description="""\
systemd Service Notification

This is a pure Python implementation of the systemd sd_notify protocol. This protocol can be used to inform systemd about service start-up completion, watchdog events, and other service status changes. Thus, this package can be used to write system services in Python that play nicely with systemd. sdnotify is compatible with both Python 2 and Python 3.
"""
)
