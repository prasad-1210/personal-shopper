## UI Server

Separate FastAPI server that talks to LangGraph over HTTP.

### Run locally (two terminals)

Terminal 1 — LangGraph agent:
    cd /path/to/personal-shopper
    langgraph dev

Terminal 2 — UI server:
    cd ui/
    cp .env.example .env
    pip install -r requirements.txt
    python server.py

Open http://localhost:22005 (set `PORT=22005` and `LANGGRAPH_URL=http://127.0.0.1:22000` in `.env` for multi-agent local dev)

### AKS deployment note

On AKS the two servers run as separate pods in the same namespace.
The UI pod talks to LangGraph pod via Kubernetes internal DNS:

    LANGGRAPH_URL=http://langgraph-service.agents-dev.svc.cluster.local:2024

No code changes needed — only the env var changes between local and AKS.
This is why the URL is never hardcoded.
