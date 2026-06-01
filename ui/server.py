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

load_dotenv()

LANGGRAPH_URL = os.environ.get("LANGGRAPH_URL", "http://127.0.0.1:22000")
LANGGRAPH_API_KEY = os.environ.get("LANGGRAPH_API_KEY", "")

app = FastAPI(title="Personal Shopper UI")

HTML_FILE = Path(__file__).parent / "index.html"


class ChatRequest(BaseModel):
    message: str
    thread_id: str = ""


class ChatResponse(BaseModel):
    reply: str
    thread_id: str
    agent_steps: list[str] = []
    constraint_violations: list[str] = []
    budget_status: str = "unchecked"
    iteration: int = 0
    run_id: str = ""
    langsmith_url: str = ""


def _langsmith_trace_url(data: dict, run_id: str) -> str:
    if not run_id:
        return ""
    langsmith = data.get("langsmith") or {}
    org_id = (langsmith.get("organization") or {}).get("id")
    project_id = (langsmith.get("tracing_project") or {}).get("id")
    if org_id and project_id:
        return (
            f"https://smith.langchain.com/o/{org_id}/projects/p/{project_id}/r/{run_id}"
        )
    project = os.environ.get("LANGSMITH_PROJECT", "")
    if project:
        return f"https://smith.langchain.com/o/-/projects/p/{project}/r/{run_id}"
    return f"https://smith.langchain.com/public/{run_id}/r"


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_FILE.read_text()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    thread_id = req.thread_id or str(uuid.uuid4())
    headers = {"Content-Type": "application/json"}
    if LANGGRAPH_API_KEY:
        headers["x-api-key"] = LANGGRAPH_API_KEY

    payload = {
        "assistant_id": "personal_shopper",
        "input": {
            "messages": [{"role": "human", "content": req.message}]
        },
        "config": {"configurable": {"thread_id": thread_id}},
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{LANGGRAPH_URL}/threads/{thread_id}/runs/wait",
                json=payload,
                headers=headers,
            )
            if response.status_code == 404:
                await client.post(
                    f"{LANGGRAPH_URL}/threads",
                    json={"thread_id": thread_id},
                    headers=headers,
                )
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
        run_id = (
            data.get("run_id")
            or (data.get("metadata") or {}).get("run_id")
            or ""
        )
        if isinstance(run_id, str):
            run_id = run_id.strip()
        else:
            run_id = str(run_id) if run_id else ""

        return ChatResponse(
            reply=reply,
            thread_id=thread_id,
            agent_steps=state.get("agent_steps", []),
            constraint_violations=state.get("constraint_violations", []),
            budget_status=state.get("budget_status", "unchecked"),
            iteration=state.get("iteration", 0),
            run_id=run_id,
            langsmith_url=_langsmith_trace_url(data, run_id),
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
