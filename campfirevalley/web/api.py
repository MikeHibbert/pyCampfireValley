"""FastAPI backend for CampfireValley web visualization interface"""

import asyncio
import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Prometheus metrics
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

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
        campfire_active_connections.set(len(self.active_connections))
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        campfire_active_connections.set(len(self.active_connections))
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)
    
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                # Remove dead connections
                self.active_connections.remove(connection)


# Prometheus metrics definitions
campfire_requests_total = Counter(
    'campfire_requests_total',
    'Total number of requests to campfires',
    ['campfire_id', 'action']
)

campfire_active_connections = Gauge(
    'campfire_active_connections',
    'Number of active WebSocket connections'
)

campfire_torch_queue_size = Gauge(
    'campfire_torch_queue_size',
    'Current torch queue size for campfires',
    ['campfire_id', 'campfire_type']
)

campfire_camper_count = Gauge(
    'campfire_camper_count',
    'Number of active campers per campfire',
    ['campfire_id', 'campfire_type']
)

campfire_processing_time = Histogram(
    'campfire_processing_time_seconds',
    'Time spent processing tasks',
    ['campfire_id', 'task_type']
)

campfire_throughput = Gauge(
    'campfire_throughput_rate',
    'Current throughput rate for campfires',
    ['campfire_id', 'campfire_type']
)

campfire_error_rate = Gauge(
    'campfire_error_rate',
    'Current error rate for campfires',
    ['campfire_id', 'campfire_type']
)


# Initialize FastAPI app
app = FastAPI(title="CampfireValley Visualization", version="1.1.0")

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

@app.get("/metrics")
async def get_metrics():
    """Prometheus metrics endpoint"""
    # Update metrics with current state
    if current_valley and visualizer:
        try:
            # Update campfire metrics
            campfires = current_valley.get_campfires()
            for campfire_id, campfire in campfires.items():
                campfire_type = getattr(campfire, 'type', 'unknown')
                
                # Update torch queue size
                torch_queue = getattr(campfire, 'torch_queue', 0)
                campfire_torch_queue_size.labels(
                    campfire_id=campfire_id, 
                    campfire_type=campfire_type
                ).set(torch_queue)
                
                # Update camper count
                camper_count = getattr(campfire, 'camper_count', 0)
                campfire_camper_count.labels(
                    campfire_id=campfire_id, 
                    campfire_type=campfire_type
                ).set(camper_count)
                
                # Update throughput (mock data for demo)
                throughput = getattr(campfire, 'throughput', 0) or (torch_queue * 2.5)
                campfire_throughput.labels(
                    campfire_id=campfire_id, 
                    campfire_type=campfire_type
                ).set(throughput)
                
                # Update error rate (mock data for demo)
                error_rate = getattr(campfire, 'error_rate', 0) or 0.02
                campfire_error_rate.labels(
                    campfire_id=campfire_id, 
                    campfire_type=campfire_type
                ).set(error_rate)
                
        except Exception as e:
            # Log error but don't fail metrics endpoint
            print(f"Error updating metrics: {e}")
    
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
    
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
    action_type = action.get("type", "unknown")
    
    # Track the request in metrics
    campfire_requests_total.labels(campfire_id=campfire_id, action=action_type).inc()
    
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    
    # Find the campfire
    campfire = current_valley.campfires.get(campfire_id)
    
    if not campfire:
        raise HTTPException(status_code=404, detail=f"Campfire {campfire_id} not found")
    
    # Perform the action
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
    for campfire_name, cf in current_valley.campfires.items():
        campfires.append({
            "id": campfire_name,
            "type": cf.__class__.__name__,
            "running": getattr(cf, '_running', False),
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
                
                # Add current task info to the state
                global current_task
                state_data = state.dict()
                if current_task:
                    state_data["current_task"] = current_task
                
                message = WebSocketMessage(
                    type="state_update",
                    data=state_data
                )
                await manager.broadcast(message.json())
                
                # Also send task-specific updates if there's an active task
                if current_task:
                    task_message = WebSocketMessage(
                        type="task_update",
                        data=current_task
                    )
                    await manager.broadcast(task_message.json())
                    
        except Exception as e:
            print(f"Error in update loop: {e}")
        
        await asyncio.sleep(2)  # Update every 2 seconds


# Task Processing Endpoints
@app.post("/api/tasks/start")
async def start_task(request: dict):
    """Start a new task for processing by campfires"""
    try:
        task_description = request.get("task", "")
        timestamp = request.get("timestamp", "")
        
        if not task_description:
            raise HTTPException(status_code=400, detail="Task description is required")
        
        # Generate a unique task ID
        import uuid
        task_id = str(uuid.uuid4())[:8]
        
        # Store task info globally for tracking
        global current_task
        current_task = {
            "id": task_id,
            "description": task_description,
            "timestamp": timestamp,
            "status": "processing"
        }
        
        # If we have a valley, we can simulate task processing
        if current_valley:
            # Simulate distributing the task to campfires
            campfires = list(current_valley.campfires.values())
            
            # For demo purposes, we'll simulate activity by updating campfire states
            import asyncio
            asyncio.create_task(simulate_task_processing(task_id, task_description, campfires))
        
        return {
            "status": "success",
            "task_id": task_id,
            "message": f"Task '{task_description}' started",
            "campfires_assigned": len(current_valley.campfires) if current_valley else 0
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting task: {str(e)}")


@app.post("/api/tasks/stop")
async def stop_task():
    """Stop the current task processing"""
    try:
        global current_task
        if current_task:
            current_task["status"] = "stopped"
            task_id = current_task["id"]
            current_task = None
            
            return {
                "status": "success",
                "message": f"Task {task_id} stopped",
                "task_id": task_id
            }
        else:
            return {
                "status": "success",
                "message": "No active task to stop"
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error stopping task: {str(e)}")


@app.get("/api/tasks/current")
async def get_current_task():
    """Get information about the current task"""
    global current_task
    if current_task:
        return current_task
    else:
        return {"status": "no_active_task"}


# Task simulation function
async def simulate_task_processing(task_id: str, task_description: str, campfires: list):
    """Simulate task processing across campfires for demo purposes"""
    try:
        import random
        import asyncio
        
        # Simulate processing stages
        stages = [
            "Analyzing task",
            "Distributing to campfires", 
            "Processing in parallel",
            "Gathering results",
            "Finalizing output"
        ]
        
        for i, stage in enumerate(stages):
            # Check if task was stopped
            global current_task
            if not current_task or current_task.get("status") == "stopped":
                break
                
            # Update task status
            if current_task:
                current_task["current_stage"] = stage
                current_task["progress"] = (i + 1) / len(stages) * 100
            
            # Simulate some campfire activity
            if campfires and len(campfires) > 0:
                active_campfire = random.choice(campfires)
                # In a real implementation, we would actually send tasks to campfires
                # For now, we just simulate activity
                
            # Wait between stages
            await asyncio.sleep(2)
        
        # Mark task as completed
        if current_task and current_task.get("status") != "stopped":
            current_task["status"] = "completed"
            current_task["current_stage"] = "Task completed"
            current_task["progress"] = 100
            
            # Auto-clear completed task after a delay
            await asyncio.sleep(5)
            if current_task and current_task.get("status") == "completed":
                current_task = None
                
    except Exception as e:
        print(f"Error in task simulation: {e}")
        if current_task:
            current_task["status"] = "error"
            current_task["error"] = str(e)


# Global task tracking
current_task = None


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