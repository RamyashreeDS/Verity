import threading
import time
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import llm
from agent import REPLAY_START, RoadWatch

app = FastAPI()
agent = RoadWatch()
app.mount("/cards", StaticFiles(directory="data/cards"), name="cards")
TICK = 0.5


def loop():
    while True:
        time.sleep(TICK)
        try:
            agent.step(TICK)
        except Exception as e:  # keep the long-running loop alive
            agent.say(f"! loop error: {e}")


threading.Thread(target=loop, daemon=True).start()
threading.Thread(target=llm.load, daemon=True).start()


def background(fn, *args):
    def run():
        try:
            fn(*args)
        except Exception as e:
            with agent.lock:
                agent.say(f"! {fn.__name__} failed: {e}")
    threading.Thread(target=run, daemon=True).start()


class Report(BaseModel):
    text: str
    kind: str = "social"


class Control(BaseModel):
    action: str
    speed: float | None = None


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/memory")
def memory_page():
    return FileResponse("static/memory.html")


@app.get("/api/state")
def state():
    return agent.snapshot()


@app.get("/api/memory")
def memory():
    return agent.memory_report()


@app.post("/api/report")
def report(r: Report):
    background(agent.ingest_text, r.text, r.kind if r.kind in ("social", "news") else "social")
    return {"ok": True}


@app.post("/api/scan_news")
def scan_news():
    background(agent.scan_news)
    return {"ok": True}


@app.post("/api/verify/{event_id}")
def verify(event_id: str):
    background(agent.verify, event_id)
    return {"ok": True}


@app.post("/api/card/{event_id}")
def card(event_id: str):
    background(agent.make_card, event_id)
    return {"ok": True}


@app.get("/api/recall")
def recall(street: str):
    return agent.recall(street)


@app.post("/api/control")
def control(c: Control):
    with agent.lock:
        if c.action == "replay":
            agent.reset(REPLAY_START, c.speed or 3600)
        elif c.action == "live":
            agent.reset(datetime.now().replace(second=0, microsecond=0), 1)
        elif c.action == "pause":
            agent.paused = not agent.paused
        elif c.action == "speed" and c.speed:
            agent.speed = c.speed
    return {"ok": True}
