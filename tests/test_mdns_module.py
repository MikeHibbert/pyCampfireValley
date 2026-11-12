"""The Valley Contract's mDNS handshake, held as unit tests (docs/valley-contract.md).

These test the record a valley builds and the announcer's re-announce loop
without touching the network: zeroconf is optional, so tests skip cleanly
when it is absent (discovery must never be load-bearing).
"""

import socket
from unittest import mock

import pytest

from campfirevalley import mdns

pytestmark = pytest.mark.skipif(
    mdns.HAS_ZEROCONF is False, reason="zeroconf is an optional extra (campfirevalley[mdns])"
)


class _StubStop:
    """A duck-typed threading.Event: drives the re-announce loop through rounds."""

    def __init__(self, rounds):
        self.rounds = rounds
        self.spans = []

    def wait(self, seconds):
        self.spans.append(seconds)
        self.rounds -= 1
        return self.rounds < 0

    def set(self):
        self.rounds = -1


def test_the_record_carries_the_contract_fields():
    info = mdns.build_service_info("Test Rig valley", 8000, path="api", addresses=["192.168.1.10"])
    assert info.type == mdns.SERVICE_TYPE
    assert info.name == f"Test Rig valley.{mdns.SERVICE_TYPE}"
    assert info.port == 8000
    recorded = {k.decode(): v.decode() for k, v in (info.properties or {}).items()}
    assert recorded["product"] == "Campfire valley"
    assert recorded["path"] == "api"


def test_the_record_carries_the_path_contract():
    # A bare valley (API at the root) must NOT bake a path into the record.
    info = mdns.build_service_info("Test Rig valley", 8000, addresses=["192.168.1.10"])
    recorded = {k.decode(): v.decode() for k, v in (info.properties or {}).items()}
    assert "path" not in recorded
    assert "product" in recorded


def test_addresses_honestly_reflect_the_host():
    addrs = mdns.v4_addresses()
    assert addrs, "a host always answers on at least one address"
    for ip in addrs:
        socket.inet_aton(ip)  # every entry must be a real dotted quad
    info = mdns.build_service_info("Test Rig valley", 8000, addresses=addrs)
    assert info.addresses, "the built record carries at least one address"


def test_the_loop_reannounces_and_stops_cleanly():
    announcer = mdns.ValleyAnnouncer(port=8000, name="Test Rig valley", every_seconds=0.0, _sleep=lambda _s: None)
    stub = _StubStop(rounds=2)
    announcer._stop = stub  # swap in the duck-typed event: no real waiting, no threads
    registered = []

    with mock.patch.object(announcer, "announce", side_effect=lambda: registered.append(1) or True):
        with mock.patch.object(announcer, "stop", wraps=announcer.stop) as stopper:
            announcer._loop()
            stopper.assert_not_called()
    assert len(registered) == 2, "two announce trips, then the loop exits on a True wait"
    assert stub.spans == [0.0, 0.0, 0.0], "the loop waited the configured gap between every round"


def test_announcer_stops_without_zeroconf_installed():
    announcer = mdns.ValleyAnnouncer(port=8000, name="Test Rig valley")
    assert announcer.stop() is None  # harmless no-op path when never announced


def test_announcer_from_env_reads_the_knobs(monkeypatch):
    monkeypatch.setenv("VALLEY_MDNS_NAME", "Named Valley")
    monkeypatch.setenv("VALLEY_MDNS_PATH", "api")
    monkeypatch.setenv("VALLEY_MDNS_PRODUCT", "Campfire valley")
    a = mdns.announcer_from_env(8001)
    assert a.name == "Named Valley"
    assert a.port == 8001
    assert a.path == "api"
    monkeypatch.delenv("VALLEY_MDNS_NAME", raising=False)
    a2 = mdns.announcer_from_env(8000)
    assert a2.name == f"{socket.gethostname()} valley"
