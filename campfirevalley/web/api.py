"""FastAPI backend for CampfireValley web visualization interface"""

import asyncio
import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from .models import VisualizationState, WebSocketMessage, NodeUpdate, ConnectionUpdate
from .visualization import ValleyVisualizer
from ..valley import Valley


class WebSocketManager:
    """Manages WebSocket connections for real-time updates"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)
    
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                # Remove dead connections
                self.active_connections.remove(connection)


# Initialize FastAPI app
app = FastAPI(title="CampfireValley Visualization", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get the correct static files path
static_path = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_path), name="static")

# WebSocket manager
manager = WebSocketManager()

# Global state
current_valley: Optional[Valley] = None
visualizer: Optional[ValleyVisualizer] = None
current_state: Optional[VisualizationState] = None


def set_valley(valley: Valley):
    """Set the valley instance for visualization"""
    global current_valley, visualizer
    current_valley = valley
    visualizer = ValleyVisualizer(valley)
    
@app.get("/", response_class=HTMLResponse)
async def get_main_page():
    """Serve the main visualization interface"""
    html_path = os.path.join(static_path, "index.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>CampfireValley Web Interface</h1><p>Static files not found. Please ensure the web interface is properly installed.</p>",
            status_code=404
        )
    
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication"""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "get_state":
                # Generate current state from valley
                if visualizer:
                    state = await visualizer.get_current_state()
                    response = WebSocketMessage(
                        type="state_update",
                        data=state.dict()
                    )
                    await manager.send_personal_message(response.json(), websocket)
                else:
                    # Send empty state
                    empty_state = VisualizationState(nodes=[], connections=[])
                    response = WebSocketMessage(
                        type="state_update",
                        data=empty_state.dict()
                    )
                    await manager.send_personal_message(response.json(), websocket)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    
@app.get("/api/valley/status")
async def get_valley_status():
    """Get current valley status"""
    if current_valley:
        return {
            "status": "active" if current_valley._running else "inactive",
            "name": current_valley.name,
            "timestamp": datetime.now().isoformat(),
            "campfires": len(current_valley.campfires),
            "active_connections": len(manager.active_connections)
        }
    else:
        return {
            "status": "no_valley",
            "timestamp": datetime.now().isoformat(),
            "campfires": 0,
            "active_connections": len(manager.active_connections)
        }
    
@app.get("/api/visualization/state")
async def get_visualization_state():
    """Get current visualization state"""
    if visualizer:
        state = await visualizer.get_current_state()
        return state.dict()
    else:
        return VisualizationState(nodes=[], connections=[]).dict()
    
@app.post("/api/campfire/{campfire_id}/action")
async def campfire_action(campfire_id: str, action: Dict):
    """Perform action on a campfire"""
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    
    # Find the campfire
    campfire = None
    for cf in current_valley.campfires:
        if cf.id == campfire_id:
            campfire = cf
            break
    
    if not campfire:
        raise HTTPException(status_code=404, detail=f"Campfire {campfire_id} not found")
    
    # Perform the action
    action_type = action.get("type")
    if action_type == "start":
        await campfire.start()
    elif action_type == "stop":
        await campfire.stop()
    elif action_type == "restart":
        await campfire.stop()
        await campfire.start()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action_type}")
    
    return {"status": "success", "campfire_id": campfire_id, "action": action}


@app.get("/api/campfires")
async def get_campfires():
    """Get list of all campfires"""
    if not current_valley:
        return []
    
    campfires = []
    for cf in current_valley.campfires:
        campfires.append({
            "id": cf.id,
            "type": cf.__class__.__name__,
            "running": cf._running,
            "camper_count": len(getattr(cf, 'campers', []))
        })
    
    return campfires


async def update_loop():
    """Background task to broadcast state updates"""
    while True:
        try:
            if visualizer and manager.active_connections:
                # Get fresh state from valley
                state = await visualizer.get_current_state()
                global current_state
                current_state = state
                
                message = WebSocketMessage(
                    type="state_update",
                    data=state.dict()
                )
                await manager.broadcast(message.json())
        except Exception as e:
            print(f"Error in update loop: {e}")
        
        await asyncio.sleep(2)  # Update every 2 seconds


@app.on_event("startup")
async def startup_event():
    """Start background tasks"""
    asyncio.create_task(update_loop())


def create_web_server(valley: Valley, host: str = "0.0.0.0", port: int = 8000):
    """Create and configure the web server for a valley"""
    set_valley(valley)
    return app


async def run_web_server(valley: Valley, host: str = "0.0.0.0", port: int = 8000):
    """Run the web server for valley visualization"""
    set_valley(valley)
    config = uvicorn.Config(app, host=host, port=port)
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    # For testing without a valley
    uvicorn.run(app, host="0.0.0.0", port=8000)