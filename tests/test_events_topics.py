"""Topic-keyed routing tests (work_8648d80e16-s1).

The bus routes by the topic derived from each event's own keys
(topic_of: torch_id -> "torch", else campfire -> "campfire", else
"valley") instead of broadcasting everything to everyone. Subscribers
declare their topics (valley/campfire/torch) and tier; ledger sinks
(topics=None or "*") subscribe to everything; live subscribers receive
only their own topics.

WHY this file exists (declared-work discipline, Father directive 19 Sep
2026, work_fb464e49b9, docs/declared-work-discipline.md): the implement
sub-verse wrote these tests as an untracked file that was never committed
and was lost; recreated in the verify sub-verse so the topic-keyed change
has executable proof, and committed this time.
"""
import asyncio

from campfirevalley.events import (
    EventBus,
    TIER_LEDGER,
    TIER_LIVE,
    ValleyEvent,
    topic_of,
)


def _drain(q):
    out = []
    while True:
        try:
            out.append(q.get_nowait())
        except asyncio.QueueEmpty:
            return out


def test_topic_of_derives_from_event_keys():
    # torch_id is the most specific key and wins over campfire.
    assert topic_of(ValleyEvent(type="tool_started", torch_id="t1")) == "torch"
    assert topic_of(ValleyEvent(type="agent_say", campfire="dev")) == "campfire"
    assert topic_of(ValleyEvent(type="valley_started")) == "valley"
    assert (
        topic_of(ValleyEvent(type="tool_started", campfire="dev", torch_id="t1"))
        == "torch"
    )


def test_live_subscriber_receives_only_declared_topics():
    bus = EventBus()
    q = bus.subscribe(topics=["torch"])
    bus.emit("tool_started", "step", torch_id="t1", tier=TIER_LIVE)
    bus.emit("agent_say", "chat", campfire="dev", tier=TIER_LIVE)
    bus.emit("valley_started", "up", tier=TIER_LIVE)
    got = _drain(q)
    assert [e.type for e in got] == ["tool_started"]


def test_ledger_sink_without_topics_receives_everything():
    bus = EventBus()
    q = bus.subscribe()  # topics=None: ledger sink / legacy caller
    bus.emit("tool_started", "step", torch_id="t1", tier=TIER_LIVE)
    bus.emit("agent_say", "chat", campfire="dev", tier=TIER_LEDGER)
    bus.emit("valley_started", "up", tier=TIER_LIVE)
    got = _drain(q)
    assert [e.type for e in got] == ["tool_started", "agent_say", "valley_started"]


def test_explicit_star_receives_everything():
    bus = EventBus()
    q = bus.subscribe(topics=["*"])
    bus.emit("tool_started", "step", torch_id="t1", tier=TIER_LIVE)
    bus.emit("valley_started", "up", tier=TIER_LIVE)
    assert len(_drain(q)) == 2


def test_string_topic_declaration_tolerated():
    bus = EventBus()
    q = bus.subscribe(topics="torch")  # bare string, not a list
    bus.emit("tool_started", "step", torch_id="t1", tier=TIER_LIVE)
    bus.emit("agent_say", "chat", campfire="dev", tier=TIER_LIVE)
    got = _drain(q)
    assert [e.type for e in got] == ["tool_started"]

    bus2 = EventBus()
    q2 = bus2.subscribe(topics="torch,valley")  # comma-separated string
    bus2.emit("tool_started", "step", torch_id="t1", tier=TIER_LIVE)
    bus2.emit("valley_started", "up", tier=TIER_LIVE)
    bus2.emit("agent_say", "chat", campfire="dev", tier=TIER_LIVE)
    got2 = _drain(q2)
    assert [e.type for e in got2] == ["tool_started", "valley_started"]


def test_multi_topic_subscriber_gets_each_declared_topic():
    bus = EventBus()
    q = bus.subscribe(topics=["torch", "valley"])
    bus.emit("tool_started", "step", torch_id="t1", tier=TIER_LIVE)
    bus.emit("valley_started", "up", tier=TIER_LIVE)
    bus.emit("agent_say", "chat", campfire="dev", tier=TIER_LIVE)
    got = _drain(q)
    assert [e.type for e in got] == ["tool_started", "valley_started"]


def test_tier_filter_still_applies_on_top_of_topics():
    bus = EventBus()
    live_q = bus.subscribe(tier=TIER_LIVE, topics=["campfire"])
    ledger_q = bus.subscribe(tier=TIER_LEDGER, topics=["campfire"])
    bus.emit("agent_say", "live chat", campfire="dev", tier=TIER_LIVE)
    bus.emit("agent_say", "ledger chat", campfire="dev", tier=TIER_LEDGER)
    # Live-tier subscriber: only live campfire events.
    assert [e.text for e in _drain(live_q)] == ["live chat"]
    # A tiered ledger subscription receives only ledger events; the full
    # torrent (both tiers) is the no-tier subscription pinned above.
    assert [e.text for e in _drain(ledger_q)] == ["ledger chat"]


def test_subscriber_count_counts_queues_not_buckets():
    bus = EventBus()
    q1 = bus.subscribe(topics=["valley", "campfire"])  # registered in 2 buckets
    q2 = bus.subscribe(topics=["torch"])
    assert bus.subscriber_count == 2  # one subscriber = one queue
    bus.unsubscribe(q1)
    assert bus.subscriber_count == 1


def test_unsubscribe_strips_every_bucket():
    bus = EventBus()
    q = bus.subscribe(topics=["torch", "valley"])
    bus.emit("tool_started", "step", torch_id="t1", tier=TIER_LIVE)
    assert len(_drain(q)) == 1
    bus.unsubscribe(q)
    bus.emit("tool_started", "step2", torch_id="t1", tier=TIER_LIVE)
    bus.emit("valley_started", "up", tier=TIER_LIVE)
    assert _drain(q) == []  # no ghost left in the remaining buckets


def test_topic_routing_uses_event_keys_not_emit_args():
    # The event's own keys decide the topic: a torch event emitted with a
    # campfire set still routes to the torch bucket (torch_id wins).
    bus = EventBus()
    torch_q = bus.subscribe(topics=["torch"])
    campfire_q = bus.subscribe(topics=["campfire"])
    bus.emit("tool_started", "step", campfire="dev", torch_id="t1", tier=TIER_LIVE)
    assert len(_drain(torch_q)) == 1
    assert _drain(campfire_q) == []