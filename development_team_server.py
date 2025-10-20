#!/usr/bin/env python3
"""
CampfireValley Development Team Server

This is the main server that runs in the Docker container to provide
the development team services via HTTP/MCP API.

The server provides endpoints for:
- Website development requests from the marketing team
- Health checks
- Status monitoring
"""

import asyncio
import json
import logging
import os
import traceback
from datetime import datetime
from typing import Dict, List, Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from campfirevalley.valley import Valley
from campfirevalley.config_manager import ConfigManager
from campfirevalley.models import Torch


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DevelopmentRequest(BaseModel):
    """Model for development requests from marketing team."""
    idea_id: str
    category: str
    strategic_requirements: str
    creative_requirements: str
    ux_requirements: str
    timestamp: str
    source_team: str


# Create FastAPI app
app = FastAPI(
    title="CampfireValley Development Team",
    description="Development team server for processing website ideas",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global valley instance
valley = None


async def initialize_valley():
    """Initialize the CampfireValley system."""
    global valley
    try:
        logger.info("Initializing CampfireValley Development Team...")
        
        # Initialize valley with development team configuration
        valley = Valley("development-team")
        await valley.start()
        
        # Provision required developer campfires
        from campfirevalley.config import CampfireConfig
        
        # Backend developer campfire
        backend_config = CampfireConfig(
            name="backend_developer",
            type="LLMCampfire",
            channels=["dev-backend", "dev-team", "auditor-review"],
            config={
                "llm": {
                    "provider": "openrouter",
                    "model": "anthropic/claude-3.5-sonnet",
                    "temperature": 0.3,
                    "max_tokens": 4000
                }
            }
        )
        await valley.provision_campfire(backend_config)
        
        # Frontend developer campfire
        frontend_config = CampfireConfig(
            name="frontend_developer",
            type="LLMCampfire",
            channels=["dev-frontend", "dev-team", "auditor-review"],
            config={
                "llm": {
                    "provider": "openrouter",
                    "model": "anthropic/claude-3.5-sonnet",
                    "temperature": 0.4,
                    "max_tokens": 4000
                }
            }
        )
        await valley.provision_campfire(frontend_config)
        
        # UX developer campfire
        ux_config = CampfireConfig(
            name="ux_developer",
            type="LLMCampfire",
            channels=["dev-ux", "dev-team", "auditor-review"],
            config={
                "llm": {
                    "provider": "openrouter",
                    "model": "anthropic/claude-3.5-sonnet",
                    "temperature": 0.5,
                    "max_tokens": 4000
                }
            }
        )
        await valley.provision_campfire(ux_config)
        
        logger.info("CampfireValley Development Team initialized successfully")
        logger.info(f"Provisioned campfires: {list(valley.get_campfires().keys())}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize valley: {str(e)}")
        logger.error(traceback.format_exc())
        return False


@app.on_event("startup")
async def startup_event():
    """Initialize the valley on startup."""
    await initialize_valley()


@app.get("/health")
def health_check():
    """Health check endpoint for Docker health checks."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "development-team",
        "valley_status": "initialized" if valley else "not_initialized"
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "CampfireValley Development Team Server",
        "status": "running",
        "endpoints": ["/health", "/api/develop_website"]
    }


@app.post("/api/develop_website")
async def develop_website(request: DevelopmentRequest):
    """Process website development requests."""
    try:
        logger.info(f"Received development request for idea: {request.idea_id}")
        
        if not valley:
            raise HTTPException(
                status_code=500, 
                detail="Development team valley not initialized"
            )
        
        # Process the development request
        result = await process_development_request(request)
        
        logger.info(f"Successfully processed idea: {request.idea_id}")
        return result
        
    except Exception as e:
        logger.error(f"Development processing failed: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Development processing failed: {str(e)}"
        )


async def process_development_request(request: DevelopmentRequest) -> Dict[str, Any]:
    """Process a development request using the valley campfires."""
    start_time = datetime.now()
    
    try:
        # Create a comprehensive development torch with all required fields
        development_torch = Torch(
            claim="website_development_request",
            source_campfire="development-team-server",
            channel="development-requests",
            torch_id=f"torch_dev_{request.idea_id}_{int(datetime.now().timestamp())}",
            sender_valley="development-team",
            target_address="valley:development-team/campfire:backend_developer",
            signature="development_team_signature",
            source="development-team-server",
            destination="backend_developer",
            content=f"""
            Website Development Request
            ==========================
            
            Idea ID: {request.idea_id}
            Category: {request.category}
            Source: {request.source_team}
            Timestamp: {request.timestamp}
            
            Strategic Requirements:
            {request.strategic_requirements}
            
            Creative Requirements:
            {request.creative_requirements}
            
            UX Requirements:
            {request.ux_requirements}
            
            Please provide a comprehensive development plan including:
            1. Technical architecture
            2. Technology stack recommendations
            3. Implementation roadmap
            4. Resource requirements
            5. Timeline estimates
            """,
            data={
                "idea_id": request.idea_id,
                "category": request.category,
                "source_team": request.source_team,
                "strategic_requirements": request.strategic_requirements,
                "creative_requirements": request.creative_requirements,
                "ux_requirements": request.ux_requirements,
                "request_timestamp": request.timestamp
            },
            metadata={
                "idea_id": request.idea_id,
                "category": request.category,
                "source_team": request.source_team,
                "request_timestamp": request.timestamp,
                "processing_timestamp": datetime.now().isoformat()
            }
        )
        
        # Process through different development campfires
        results = {}
        
        # Get available campfires
        available_campfires = valley.get_campfires()
        
        # Backend development analysis
        if "backend_developer" in available_campfires:
            backend_result = await valley.process_torch(development_torch)
            results["backend_analysis"] = backend_result
        
        # Frontend development analysis  
        if "frontend_developer" in available_campfires:
            # Update target for frontend
            frontend_torch = Torch(
                claim="website_development_request",
                source_campfire="development-team-server",
                channel="development-requests",
                torch_id=f"torch_frontend_{request.idea_id}_{int(datetime.now().timestamp())}",
                sender_valley="development-team",
                target_address="valley:development-team/campfire:frontend_developer",
                signature="development_team_signature",
                source="development-team-server",
                destination="frontend_developer",
                data=development_torch.data,
                metadata=development_torch.metadata
            )
            frontend_result = await valley.process_torch(frontend_torch)
            results["frontend_analysis"] = frontend_result
        
        # UX development analysis
        if "ux_developer" in available_campfires:
            # Update target for UX
            ux_torch = Torch(
                claim="website_development_request",
                source_campfire="development-team-server",
                channel="development-requests",
                torch_id=f"torch_ux_{request.idea_id}_{int(datetime.now().timestamp())}",
                sender_valley="development-team",
                target_address="valley:development-team/campfire:ux_developer",
                signature="development_team_signature",
                source="development-team-server",
                destination="ux_developer",
                data=development_torch.data,
                metadata=development_torch.metadata
            )
            ux_result = await valley.process_torch(ux_torch)
            results["ux_analysis"] = ux_result
        
        # If no specific campfires, use general processing
        if not results:
            general_result = await valley.process_torch(development_torch)
            results["general_analysis"] = general_result
        
        # Calculate processing time
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # Prepare response
        response = {
            "idea_id": request.idea_id,
            "status": "completed",
            "processing_time_seconds": processing_time,
            "timestamp": datetime.now().isoformat(),
            "development_analysis": results,
            "summary": {
                "total_analyses": len(results),
                "campfires_used": list(results.keys()),
                "recommendation": "Development plan generated successfully"
            }
        }
        
        # Log the successful processing
        logger.info(f"Development request {request.idea_id} processed in {processing_time:.2f}s")
        
        return response
        
    except Exception as e:
        logger.error(f"Error processing development request: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Return error response
        return {
            "idea_id": request.idea_id,
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
            "processing_time_seconds": (datetime.now() - start_time).total_seconds()
        }


if __name__ == "__main__":
    logger.info("Starting CampfireValley Development Team Server...")
    
    # Get configuration from environment
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    
    # Run the server
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )