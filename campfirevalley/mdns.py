"""Announce this valley on the local network (mDNS/DNS-SD).

Half of the Valley Contract's handshake (docs/valley-contract.md): AndruIDE
listens for `_campfire._tcp.local.` announcements and lists the valleys it
hears; this module is the announcing end, as part of the library (Father,
12 Nov 2026: the valley must be findable on the network by default).

WHY network-multicast, not just loopback: the IDE may live in a browser
window or another process; discovery is how a new user finds their valley
without typing addresses. The announcer is deliberately independent of any
web server lifecycle: it keeps re-farming the record hourly so late-joining
listeners hear it, and unregisters cleanly on stop.

Optional dependency: `pip install campfirevalley[mdns]` (zeroconf).
Without zeroconf, announce() returns False and the valley still serves;
discovery is a convenience, never a load-bearing path.
"""

import os
import socket
import threading
import time
from typing import Callable, List, Optional

SERVICE_TYPE = "_campfire._tcp.local."

try:
    from zeroconf import ServiceInfo, Zeroconf

    HAS_ZEROCONF = True
except ImportError:
    HAS_ZEROCONF = False

DEFAULT_PRODUCT = "Campfire valley"
DEFAULT_PATH = ""   # bare valley serves the contract at the root (no proxy prefix)


def v4_addresses() -> List[str]:
    """Every IPv4 address this host answers on (to include in the record)."""
    addrs = set()
    hostname = socket.gethostname()
    try:
        for info in socket.getaddrinfo(hostname, None, family=socket.AF_INET):
            ip = str(info[4][0])
            if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
                addrs.add(ip)
    except OSError:
        pass
    # A host without a LAN address (no network yet) still loops back fine.
    if not addrs:
        addrs.add("127.0.0.1")
    return sorted(addrs)


def default_name() -> str:
    """The instance name a valley advertises as: '<hostname> valley'."""
    return f"{socket.gethostname()} valley"


def build_service_info(
    instance_name: str,
    port: int,
    path: str = DEFAULT_PATH,
    product: str = DEFAULT_PRODUCT,
    addresses: Optional[List[str]] = None,
):
    """The record a valley serves; pure so tests can hold it without a network."""
    server = f"{socket.gethostname().lower()}.local."
    properties = {"product": product}
    if path:
        properties["path"] = path
    return ServiceInfo(
        SERVICE_TYPE,
        f"{instance_name}.{SERVICE_TYPE}",
        server=server,
        addresses=[socket.inet_aton(a) for a in (addresses if addresses is not None else v4_addresses())],
        port=port,
        properties=properties,
    )


class ValleyAnnouncer:
    """Registers the valley on the network and keeps the record fresh until stopped."""

    def __init__(self, port: int, name: Optional[str] = None, path: str = DEFAULT_PATH,
                 product: str = DEFAULT_PRODUCT, every_seconds: float = 3600.0,
                 _sleep: Callable[[float], None] = time.sleep):
        self.port = port
        self.name = name or default_name()
        self.path = path
        self.product = product
        self.every_seconds = every_seconds
        self._sleep = _sleep          # injectable so tests never wait real time
        self._zc = None
        self._info = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def announce(self) -> bool:
        """Register once. False when zeroconf is unavailable — still harmless."""
        if not HAS_ZEROCONF:
            return False
        if self._zc is None:
            self._zc = Zeroconf()
        if self._info is not None:
            self._unregister()
        self._info = build_service_info(self.name, self.port, self.path, self.product)
        self._zc.register_service(self._info, allow_name_change=False)
        return True

    def start_background(self) -> bool:
        """Announce now, then re-announce every `every_seconds` on a daemon thread."""
        if not self.announce():
            return False
        thread = threading.Thread(target=self._loop, name="valley-mdns", daemon=True)
        thread.start()
        self._thread = thread
        return True

    def _loop(self) -> None:
        deadline = self.every_seconds
        while not self._stop.wait(deadline):
            # Re-check the interface list each round: networks change while running.
            self.announce()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        self._unregister()
        if self._zc is not None:
            self._zc.close()
            self._zc = None

    def _unregister(self) -> None:
        if self._zc is not None and self._info is not None:
            try:
                self._zc.unregister_service(self._info)
            except Exception:
                pass
            self._info = None


def announcer_from_env(port: int) -> ValleyAnnouncer:
    """Build the announcer from the env knobs the contract documents."""
    return ValleyAnnouncer(
        port=port,
        name=os.getenv("VALLEY_MDNS_NAME"),
        path=os.getenv("VALLEY_MDNS_PATH", DEFAULT_PATH),
        product=os.getenv("VALLEY_MDNS_PRODUCT", DEFAULT_PRODUCT),
    )
