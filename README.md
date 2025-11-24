# Realtime Chat App

FastAPI + WebSocket chat application with emoji reactions, ready for local development or container deployment.

## Local development

```powershell
cd C:\Users\rk\Desktop\Chat\realtime-chat-app
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` to interact with the chat UI.

## Docker deployment

```powershell
cd C:\Users\rk\Desktop\Chat\realtime-chat-app
docker build -t realtime-chat .
docker run -p 8000:8000 realtime-chat
```

The container exposes port `8000` and uses `uvicorn` as the entrypoint.

## Railway / Nixpacks

`railway.json` already includes:

- Builder: Nixpacks (no extra config needed)
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port ${PORT}`
- Health check path: `/`

Push this repository to Railway and it will pick up the config automatically.

## Frontend-only hosts (e.g. Vercel)

The browser connects to `/ws/...` on the same host by default. When you deploy the FastAPI backend somewhere else (Railway, Fly, etc.) and serve only the static files on a platform such as Vercel, set the `WS_BASE_URL` environment variable before starting FastAPI:

```powershell
setx WS_BASE_URL "wss://your-backend-hostname"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The frontend will use that URL for WebSocket traffic while the rest of the assets can continue to be served from the static host.

