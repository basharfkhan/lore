"""Web service for LORE: one page, a streaming question endpoint and pre-computed examples.

    uvicorn lore.serve.app:app --port 8000

POST /api/ask streams server-sent events while the agent works: a ``step`` for each tool call,
then ``answer`` with the report, its sources and its cost. Conversations are kept in memory for
follow-up questions; they are small and losing them on restart only ends a chat.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from lore.agent.premortem import DEFAULT_MODEL, run
from lore.paths import ROOT
from lore.serve import corpus
from lore.serve.budget import DAILY_CAP_USD, RateLimiter, spend_store

WEB_DIR = ROOT / "web"
MAX_QUESTION_CHARS = 2000
MAX_TURNS_PER_CHAT = 5
SESSION_TTL_SECONDS = 3600
MAX_SESSIONS = 200

corpus.ensure()
app = FastAPI(title="LORE", docs_url=None, redoc_url=None)
spend = spend_store()
limiter = RateLimiter()
sessions: dict[str, dict] = {}
sessions_lock = threading.Lock()


class Ask(BaseModel):
    question: str = Field(min_length=10, max_length=MAX_QUESTION_CHARS)
    session_id: str | None = None


def _event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


def _session(session_id: str | None) -> tuple[str, dict]:
    now = time.time()
    with sessions_lock:
        for key in [k for k, s in sessions.items() if now - s["seen"] > SESSION_TTL_SECONDS]:
            del sessions[key]
        if session_id in sessions:
            sessions[session_id]["seen"] = now
            return session_id, sessions[session_id]
        if len(sessions) >= MAX_SESSIONS:
            del sessions[min(sessions, key=lambda k: sessions[k]["seen"])]
        new_id = uuid.uuid4().hex
        sessions[new_id] = {"messages": [], "sources": {}, "turns": 0, "seen": now}
        return new_id, sessions[new_id]


def _refusal(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/status")
def status() -> dict:
    spent = spend.spent_today()
    return {
        "model": DEFAULT_MODEL,
        "daily_cap_usd": DAILY_CAP_USD,
        "live_available": spent < DAILY_CAP_USD,
    }


@app.get("/api/examples")
def examples() -> FileResponse:
    return FileResponse(WEB_DIR / "examples.json", media_type="application/json")


@app.post("/api/ask")
def ask(body: Ask, request: Request):
    visitor = request.headers.get("x-forwarded-for", request.client.host).split(",")[0].strip()
    if spend.spent_today() >= DAILY_CAP_USD:
        return _refusal(
            "Today's budget for live questions is used up. The examples still work, and live "
            "questions reopen at midnight UTC.",
            429,
        )
    if not limiter.allow(visitor):
        return _refusal("You have asked several questions this hour. Try again later.", 429)
    session_id, session = _session(body.session_id)
    if session["turns"] >= MAX_TURNS_PER_CHAT:
        return _refusal("This conversation has reached its limit. Start a new one.", 429)

    events: queue.Queue = queue.Queue()

    def work() -> None:
        try:
            result = run(
                body.question,
                history=session["messages"],
                sources=session["sources"],
                on_step=lambda step: events.put(("step", step)),
            )
            spend.add(result.cost_usd)
            session["messages"] = result.messages
            session["sources"] = result.sources
            session["turns"] += 1
            events.put(
                (
                    "answer",
                    {
                        "session_id": session_id,
                        "answer": result.answer,
                        "sources": result.sources,
                        "unsupported_links": result.unsupported_links,
                        "cost_usd": result.cost_usd,
                        "tool_calls": len(result.steps),
                        "model": result.model,
                        "turns_left": MAX_TURNS_PER_CHAT - session["turns"],
                    },
                )
            )
        except Exception as exc:  # the stream must end with something the page can show
            events.put(("error", {"error": f"{type(exc).__name__}: the request failed."}))
        events.put(None)

    threading.Thread(target=work, daemon=True).start()

    def stream():
        while (item := events.get()) is not None:
            yield _event(*item)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(Path(WEB_DIR / "index.html"))
