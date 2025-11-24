import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Dict, List, Union, Optional
from starlette.requests import Request
from datetime import datetime
from pathlib import Path
import uvicorn, json, uuid
from pydantic import ValidationError
from .schemas import Message, MessageBroadcast, ReactionRequest, MessageRequest, ReactionData, AddReactionRequest, RemoveReactionRequest

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI()

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

class ConnectionManager:
    def __init__(self):
        self.rooms: Dict[str, List[WebSocket]] = {}
        self.users: Dict[str, Dict[str, str]] = {}   # room ➞ {ws_id: username}
        self.messages: Dict[str, Dict[str, Message]] = {}  # room ➞ {message_id: Message}

    async def connect(self, room: str, username: str, websocket: WebSocket):
        await websocket.accept()
        self.rooms.setdefault(room, []).append(websocket)
        self.users.setdefault(room, {})[id(websocket)] = username
        await self.broadcast(room, {"type": "join", "user": username, "online": list(self.users[room].values())})

    async def disconnect(self, room: str, websocket: WebSocket):
        if room in self.rooms and websocket in self.rooms[room]:
            self.rooms[room].remove(websocket)
            if room in self.users and id(websocket) in self.users[room]:
                username = self.users[room].pop(id(websocket))
                await self.broadcast(room, {"type": "leave", "user": username, "online": list(self.users[room].values())})
            if not self.rooms[room]:
                del self.rooms[room]
                if room in self.users:
                    del self.users[room]

    def store_message(self, room: str, message: Message) -> None:
        """Store a message in the room's message history"""
        self.messages.setdefault(room, {})[message.id] = message
    
    def get_message(self, room: str, message_id: str) -> Optional[Message]:
        """Get a specific message by ID"""
        return self.messages.get(room, {}).get(message_id)
    
    def verify_user_in_room(self, room: str, username: str) -> bool:
        """Verify that a user is currently connected to the room"""
        if room not in self.users:
            return False
        return username in self.users[room].values()
    
    def add_reaction(self, room: str, message_id: str, emoji: str, username: str) -> bool:
        """Add a reaction to a message. Returns True if successful."""
        message = self.get_message(room, message_id)
        if not message:
            return False
        
        if emoji not in message.reactions.emoji:
            message.reactions.emoji[emoji] = []
        
        if username not in message.reactions.emoji[emoji]:
            message.reactions.emoji[emoji].append(username)
        
        return True
    
    def remove_reaction(self, room: str, message_id: str, emoji: str, username: str) -> bool:
        """Remove a reaction from a message. Returns True if successful."""
        message = self.get_message(room, message_id)
        if not message:
            return False
        
        if emoji in message.reactions.emoji and username in message.reactions.emoji[emoji]:
            message.reactions.emoji[emoji].remove(username)
            # Remove emoji key if no users have this reaction
            if not message.reactions.emoji[emoji]:
                del message.reactions.emoji[emoji]
            return True
        
        return False

    async def broadcast(self, room: str, message: Union[dict, MessageBroadcast]):
        """Broadcast a message to all clients in a room"""
        if room in self.rooms:
            # Convert to dict if it's a Pydantic model
            if isinstance(message, MessageBroadcast):
                message_data = message.model_dump(exclude_none=True)
                # Convert datetime to ISO string for JSON serialization
                if "timestamp" in message_data and message_data["timestamp"]:
                    message_data["timestamp"] = message_data["timestamp"].isoformat()
                # Convert reactions to dict format
                if "reactions" in message_data and message_data["reactions"]:
                    message_data["reactions"] = message_data["reactions"]["emoji"]
            else:
                message_data = message
            
            message_text = json.dumps(message_data)
            disconnected = []
            for websocket in self.rooms[room]:
                try:
                    await websocket.send_text(message_text)
                except:
                    disconnected.append(websocket)
            
            # Clean up disconnected websockets
            for websocket in disconnected:
                await self.disconnect(room, websocket)

manager = ConnectionManager()

@app.get("/")
async def get_index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "ws_base_url": os.environ.get("WS_BASE_URL", "").strip(),
        },
    )

@app.websocket("/ws/{room}/{username}")
async def websocket_endpoint(websocket: WebSocket, room: str, username: str):
    await manager.connect(room, username, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if message_data["type"] == "message":
                try:
                    # Validate and create message
                    message_request = MessageRequest(**message_data)
                except ValidationError:
                    continue  # Skip invalid messages
                
                # Create and store message with reactions
                message_id = str(uuid.uuid4())
                message = Message(
                    id=message_id,
                    type="message",
                    user=username,
                    content=message_request.content,
                    timestamp=datetime.now(),
                    reactions=ReactionData()
                )
                
                manager.store_message(room, message)
                
                # Broadcast message to all clients
                broadcast_message = MessageBroadcast(
                    type="message",
                    user=username,
                    content=message_request.content,
                    message_id=message_id,
                    reactions=message.reactions,
                    timestamp=message.timestamp
                )
                
                await manager.broadcast(room, broadcast_message)
                
            elif message_data["type"] == "add_reaction":
                try:
                    # Validate add_reaction request
                    add_reaction_request = AddReactionRequest(**message_data)
                except ValidationError:
                    continue  # Skip invalid add_reaction

                # Verify user is in the room
                if not manager.verify_user_in_room(room, username):
                    continue  # Skip if user not verified

                # Add reaction and broadcast
                success = manager.add_reaction(
                    room, add_reaction_request.message_id, 
                    add_reaction_request.emoji, username
                )

                if success:
                    updated_message = manager.get_message(room, add_reaction_request.message_id)
                    if updated_message:
                        # Get users for this specific emoji
                        users_for_emoji = updated_message.reactions.emoji.get(add_reaction_request.emoji, [])
                        
                        reaction_update = MessageBroadcast(
                            type="reaction_update",
                            user=username,
                            message_id=add_reaction_request.message_id,
                            emoji=add_reaction_request.emoji,
                            users=users_for_emoji,
                            reactions=updated_message.reactions
                        )
                        await manager.broadcast(room, reaction_update)

            elif message_data["type"] == "remove_reaction":
                try:
                    # Validate remove_reaction request
                    remove_reaction_request = RemoveReactionRequest(**message_data)
                except ValidationError:
                    continue  # Skip invalid remove_reaction

                # Verify user is in the room
                if not manager.verify_user_in_room(room, username):
                    continue  # Skip if user not verified

                # Remove reaction and broadcast
                success = manager.remove_reaction(
                    room, remove_reaction_request.message_id,
                    remove_reaction_request.emoji, username
                )

                if success:
                    updated_message = manager.get_message(room, remove_reaction_request.message_id)
                    if updated_message:
                        # Get users for this specific emoji (empty list if removed completely)
                        users_for_emoji = updated_message.reactions.emoji.get(remove_reaction_request.emoji, [])
                        
                        reaction_update = MessageBroadcast(
                            type="reaction_update",
                            user=username,
                            message_id=remove_reaction_request.message_id,
                            emoji=remove_reaction_request.emoji,
                            users=users_for_emoji,
                            reactions=updated_message.reactions
                        )
                        await manager.broadcast(room, reaction_update)
                        
            elif message_data["type"] == "reaction":
                try:
                    # Validate reaction request
                    reaction_request = ReactionRequest(**message_data)
                except ValidationError:
                    continue  # Skip invalid reactions
                
                # Handle reaction add/remove
                success = False
                if reaction_request.action == "add":
                    success = manager.add_reaction(
                        room, reaction_request.message_id, 
                        reaction_request.emoji, username
                    )
                elif reaction_request.action == "remove":
                    success = manager.remove_reaction(
                        room, reaction_request.message_id,
                        reaction_request.emoji, username
                    )
                
                if success:
                    # Get updated message and broadcast reaction update
                    updated_message = manager.get_message(room, reaction_request.message_id)
                    if updated_message:
                        # Get users for this specific emoji
                        users_for_emoji = updated_message.reactions.emoji.get(reaction_request.emoji, [])
                        
                        reaction_update = MessageBroadcast(
                            type="reaction_update",
                            user=username,
                            message_id=reaction_request.message_id,
                            emoji=reaction_request.emoji,
                            users=users_for_emoji,
                            reactions=updated_message.reactions
                        )
                        await manager.broadcast(room, reaction_update)
                        
    except WebSocketDisconnect:
        await manager.disconnect(room, websocket)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
