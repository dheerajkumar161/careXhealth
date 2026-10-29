"""SSE: a notification created by another actor reaches the open stream; unauthenticated callers are refused."""
import threading
import time

from conftest import draft_and_approve


def test_stream_requires_auth(fresh):  # noqa: ANN001
    assert fresh.get("/api/stream?maxSeconds=1").status_code == 401


def test_stream_delivers_new_notification(api, fresh):  # noqa: ANN001
    patient, doctor = api("patient"), api("doctor")
    events: list[str] = []

    def listen() -> None:
        with fresh.stream("GET", "/api/stream?maxSeconds=8", headers=patient._h()) as r:
            assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
            for line in r.iter_lines():
                if line.startswith("event:"):
                    events.append(line.split(":", 1)[1].strip())
                if "notification" in events:
                    break

    th = threading.Thread(target=listen)
    th.start()
    time.sleep(1)
    draft_and_approve(doctor)  # the Communication agent notifies the patient their plan is ready
    th.join(timeout=15)
    assert events[0] == "ready" and "notification" in events
