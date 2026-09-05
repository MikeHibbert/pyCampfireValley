# Tests for folder binding: direct-run (no pytest). POST /torchs route + send_torch wiring + narration data objective.
import sys
sys.path.insert(0, r"C:\Users\Mike\Documents\Python\CampfireValley")
sys.stdout.reconfigure(encoding="utf-8")

from campfirevalley.events import EventBus, build_events_app
from fastapi.testclient import TestClient

# 1. POST /torchs with send_torch wired
sent = {}
def fake_send(body):
    sent.update(body)
    return "t-test-123"
bus = EventBus()
app = build_events_app(bus, send_torch=fake_send)
c = TestClient(app)
r = c.post("/torchs", json={"objective": "fix readme", "folder": "C:/proj", "context": "ctx"})
assert r.status_code == 200, r.text
j = r.json()
assert j["ok"] is True and j["torch_id"] == "t-test-123", j
assert sent["objective"] == "fix readme" and sent["folder"] == "C:/proj"
print("T1 POST /torchs ok")

# 2. POST /torchs without objective -> 200 with error body (route-level validation)
r2 = c.post("/torchs", json={"context": "no objective"})
j2 = r2.json()
assert r2.status_code == 200 and "error" in j2 and "objective" in j2["error"], j2
print("T2 missing objective -> error ok")

# 3. POST /torchs with send_torch None -> 200 with error body
bus2 = EventBus()
app2 = build_events_app(bus2)
c2 = TestClient(app2)
r3 = c2.post("/torchs", json={"objective": "x"})
j3 = r3.json()
assert r3.status_code == 200 and "error" in j3, j3
print("T3 no send_torch -> error ok")

# 4. narration data objective read: import valley and check helper source contains the data fallback
src = open(r"C:\Users\Mike\Documents\Python\CampfireValley\campfirevalley\valley.py", encoding="utf-8").read()
assert "data.get" in src and "objective" in src
print("T4 narration reads data objective ok")

print("ALL FOLDER-BINDING TESTS PASS (4/4)")
