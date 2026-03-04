from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from src.api.controllers import DetectionController
import asyncio
import json
from datetime import datetime

router = APIRouter()
controller = DetectionController()

@router.get("/api/events/stream")
async def events_stream(
    camera_id: list[str] = Query(default=[], alias="camera_id[]"),
    start_time: str | None = Query(None),
    end_time: str | None = Query(None),
):
    """
    Server-Sent Events (SSE) endpoint for real-time detection events
    """
    
    async def event_generator():
        try:
            # Send initial connection message
            msg = json.dumps({
                "type": "connected",
                "timestamp": datetime.now().isoformat(),
                "message": "Event stream connected"
            })
            yield f"data: {msg}\n\n"
            
            # Keep connection alive with periodic heartbeat
            while True:
                await asyncio.sleep(30)  # 30 seconds heartbeat
                msg = json.dumps({
                    "type": "heartbeat",
                    "timestamp": datetime.now().isoformat()
                })
                yield f"data: {msg}\n\n"
                
        except asyncio.CancelledError:
            # Client disconnected
            msg = json.dumps({
                "type": "disconnected",
                "timestamp": datetime.now().isoformat()
            })
            yield f"data: {msg}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET",
            "Access-Control-Allow-Headers": "Content-Type",
        }
    )