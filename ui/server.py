"""
Personal Shopper UI Server.
Serves index.html and proxies chat requests to LangGraph agent.
"""
import os
import uuid
import httpx
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
# Repo .env (LangSmith) then ui/.env (LANGGRAPH_URL, PORT) — latter wins on conflict
load_dotenv(ROOT / ".env")
load_dotenv(Path(__file__).parent / ".env")

LANGGRAPH_URL = os.environ.get("LANGGRAPH_URL", "http://127.0.0.1:22000")
LANGGRAPH_API_KEY = os.environ.get("LANGGRAPH_API_KEY", "")

app = FastAPI(title="Personal Shopper UI")

HTML_FILE = Path(__file__).parent / "index.html"


class ChatRequest(BaseModel):
    message: str
    thread_id: str = ""


class SessionResponse(BaseModel):
    thread_id: str


class ChatResponse(BaseModel):
    reply: str
    thread_id: str
    agent_steps: list[str] = []
    constraint_violations: list[str] = []
    budget_status: str = "unchecked"
    iteration: int = 0
    run_id: str = ""
    langsmith_url: str = ""


def _langsmith_trace_url(run_id: str) -> str:
    """Build a LangSmith run URL. LangGraph run_id == LangSmith root run UUID."""
    if not run_id:
        return ""
    try:
        from langsmith import Client

        run = Client().read_run(run_id)
        if run.url:
            return str(run.url).split("?")[0]  # drop poll/query params for a stable link
    except Exception:
        pass
    # Fallback: project name in path is unreliable; public run link still works when logged in
    return f"https://smith.langchain.com/public/{run_id}/r"


def _request_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if LANGGRAPH_API_KEY:
        headers["x-api-key"] = LANGGRAPH_API_KEY
    return headers


def _run_config(thread_id: str) -> dict:
    """One LangGraph thread per UI chat; same ids for checkpoint + LangSmith grouping."""
    return {
        "configurable": {"thread_id": thread_id},
        "metadata": {
            "thread_id": thread_id,
            "session_id": thread_id,
            "conversation_id": thread_id,
        },
        "tags": [f"thread:{thread_id[:8]}"],
    }


async def _ensure_langgraph_thread(
    client: httpx.AsyncClient, thread_id: str, headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{LANGGRAPH_URL}/threads",
        json={"thread_id": thread_id},
        headers=headers,
    )
    if response.status_code not in (200, 201, 409):
        raise HTTPException(
            status_code=502,
            detail=f"Could not create LangGraph thread: {response.status_code}",
        )


async def _latest_thread_run_id(
    client: httpx.AsyncClient, thread_id: str, headers: dict[str, str]
) -> str:
    """
    /runs/wait returns graph output only (no run_id). Fetch the latest run on the thread.
    """
    response = await client.get(
        f"{LANGGRAPH_URL}/threads/{thread_id}/runs",
        params={"limit": 1},
        headers=headers,
    )
    if response.status_code != 200:
        return ""
    runs = response.json()
    if not runs:
        return ""
    if isinstance(runs, dict):
        runs = runs.get("runs") or runs.get("data") or []
    if not runs:
        return ""
    latest = runs[0] if isinstance(runs[0], dict) else {}
    return str(latest.get("run_id") or "")


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_FILE.read_text()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/session", response_model=SessionResponse)
async def create_session() -> SessionResponse:
    """Create a LangGraph thread for a new UI chat (all messages in chat use this id)."""
    thread_id = str(uuid.uuid4())
    headers = _request_headers()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            await _ensure_langgraph_thread(client, thread_id, headers)
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to LangGraph server. Is langgraph dev running?",
        )
    return SessionResponse(thread_id=thread_id)


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    thread_id = (req.thread_id or "").strip() or str(uuid.uuid4())
    headers = _request_headers()

    payload = {
        "assistant_id": "personal_shopper",
        "input": {
            "messages": [{"type": "human", "content": req.message}],
        },
        "config": _run_config(thread_id),
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            await _ensure_langgraph_thread(client, thread_id, headers)
            response = await client.post(
                f"{LANGGRAPH_URL}/threads/{thread_id}/runs/wait",
                json=payload,
                headers=headers,
            )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"LangGraph error {response.status_code}: {response.text[:300]}"
                )

            data = response.json()
            run_id = await _latest_thread_run_id(client, thread_id, headers)

            outputs = data.get("outputs") or data.get("output") or data
            if isinstance(outputs, dict) and "output" in outputs:
                outputs = outputs["output"]

            reply = ""
            messages = outputs.get("messages", []) if isinstance(outputs, dict) else []
            for m in reversed(messages):
                content = m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")
                msg_type = m.get("type", "") if isinstance(m, dict) else getattr(m, "type", "")
                if msg_type in ("ai", "AIMessage") and content:
                    reply = content
                    break

            if not reply:
                reply = "I couldn't generate a shopping list. Please try again."

            state = outputs if isinstance(outputs, dict) else {}

            return ChatResponse(
                reply=reply,
                thread_id=thread_id,
                agent_steps=state.get("agent_steps", []),
                constraint_violations=state.get("constraint_violations", []),
                budget_status=state.get("budget_status", "unchecked"),
                iteration=state.get("iteration", 0),
                run_id=run_id.strip(),
                langsmith_url=_langsmith_trace_url(run_id),
            )

    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to LangGraph server. Is langgraph dev running?"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 22005))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
