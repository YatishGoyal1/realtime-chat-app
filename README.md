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

