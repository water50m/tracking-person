"""
Dashboard API
- GET /api/dashboard/cameras           — list cameras + active-stream status
- GET /api/dashboard/mjpeg/{camera_id} — MJPEG live relay from RTSP
- GET /api/dashboard/latest-detections/{camera_id} — last N detections for overlay
"""

from __future__ import annotations

import cv2
import os
import asyncio
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse

from src.services.database import DatabaseService
from src.services.stream_manager import stream_manager
from src.api.video_controller import _ACTIVE_STREAMS, YOUTUBE_PATTERN, _extract_youtube_stream, _register_stream, _unregister_stream
from src.services.ai_processor import process_video_task

router = APIRouter()

MINIO_BASE = os.getenv("MINIO_BASE_URL", "http://myserver:9000")

# ─── Cameras ──────────────────────────────────────────────────────────────────

@router.get("/cameras")
async def list_dashboard_cameras():
    """Return all cameras from DB merged with active-stream registry."""
    try:
        db = DatabaseService()
        with db.conn.cursor() as cur:
            cur.execute("SELECT id, name, source_url, is_active FROM cameras ORDER BY id")
            rows = cur.fetchall()
        cameras = [
            {
                "id": row[0],
                "name": row[1],
                "source_url": row[2],
                "is_active": row[3],
                "is_processing": str(row[0]) in _ACTIVE_STREAMS,
                "is_prediction_paused": stream_manager.is_prediction_paused(str(row[0])),
            }
            for row in rows
        ]
        return {"cameras": cameras}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Latest detections ────────────────────────────────────────────────────────

@router.get("/latest-detections/{camera_id}")
async def latest_detections(camera_id: str, limit: int = Query(8, ge=1, le=50)):
    """Return the most recent N detections for a given camera_id."""
    try:
        db = DatabaseService()
        with db.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, track_id, timestamp, image_path,
                       clothing_category, class_name, color_profile
                FROM detections
                WHERE camera_id = %s
                ORDER BY timestamp DESC
                LIMIT %s
                """,
                (camera_id, limit),
            )
            rows = cur.fetchall()
        return {
            "camera_id": camera_id,
            "detections": [
                {
                    "id": str(row[0]),
                    "track_id": row[1],
                    "timestamp": row[2].isoformat() if row[2] else None,
                    "image_url": f"{MINIO_BASE}/{row[3]}" if row[3] else None,
                    "category": row[4] or "UNKNOWN",
                    "class_name": row[5] or "unknown",
                    "color_profile": row[6] or {},
                }
                for row in rows
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── MJPEG relay ──────────────────────────────────────────────────────────────

_MJPEG_CACHE: dict[str, str] = {}   # camera_id → rtsp_url (cached from DB)


def _get_rtsp_url(camera_id: str) -> str | None:
    """Look up the RTSP stream URL for a camera_id from the DB (or int for webcam)."""
    if camera_id in _MJPEG_CACHE:
        return _MJPEG_CACHE[camera_id]
    try:
        db = DatabaseService()
        with db.conn.cursor() as cur:
            cur.execute("SELECT source_url FROM cameras WHERE id = %s", (camera_id,))
            row = cur.fetchone()
        if row and row[0]:
            _MJPEG_CACHE[camera_id] = row[0]
            return row[0]
    except Exception:
        pass
    return None


async def _mjpeg_generator(source: str, camera_id: str) -> AsyncGenerator[bytes, None]:
    """Open a video source with OpenCV and yield MJPEG boundary frames."""
    loop = asyncio.get_event_loop()

    # If AI processing is active for this camera, stream from the global cache
    if camera_id in _ACTIVE_STREAMS:
        while camera_id in _ACTIVE_STREAMS:
            frame_bytes = stream_manager.get_frame(camera_id)
            if frame_bytes:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame_bytes
                    + b"\r\n"
                )
            await asyncio.sleep(1 / 15)  # Yield loop heavily to prevent blocking
        return  # Exit when AI processing stops
                
    # If not active, do not occupy the server. The frontend handles native playback.
    return
    if not cap.isOpened():
        cap.release()
        return



@router.get("/mjpeg/{camera_id}")
async def mjpeg_stream(camera_id: str):
    """
    Stream live MJPEG from the camera's source_url or from the global shared buffer if AI is processing.
    Browser just needs: <img src="/api/dashboard/mjpeg/{camera_id}">
    """
    source = _get_rtsp_url(camera_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not found or has no source URL")

    return StreamingResponse(
        _mjpeg_generator(source, camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "close",
        }
    )

# ─── Prediction Controls ──────────────────────────────────────────────────────

@router.post("/prediction/{camera_id}/stop")
async def stop_prediction(camera_id: str):
    """Stop AI processing for a camera entirely and return to inactive state."""
    event = _ACTIVE_STREAMS.get(camera_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Camera is not currently processing")
    
    # 1. Trigger the stop event to kill the background task loop in ai_processor
    event.set()
    
    # 2. Wait a moment for it to gracefully exit
    await asyncio.sleep(0.5)
    
    # 3. Clean up stream manager memory cache so old frames don't reappear later
    stream_manager.clear_camera(camera_id)
    
    return {"status": "success", "camera_id": camera_id, "message": "Prediction stopped"}

@router.post("/prediction/{camera_id}/start")
async def start_prediction(camera_id: str, background_tasks: BackgroundTasks):
    """Manually start AI processing for a camera that is currently inactive."""
    if camera_id in _ACTIVE_STREAMS:
        raise HTTPException(status_code=400, detail="Camera is already processing")

    source = _get_rtsp_url(camera_id)
    if not source:
        raise HTTPException(status_code=404, detail="Camera has no source URL")

    # If it's a YouTube link, we extract the stream URL
    if YOUTUBE_PATTERN.search(source):
        try:
            info = _extract_youtube_stream(source)
            stream_url = info["stream_url"]
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"yt-dlp error: {e}")
    else:
        stream_url = source

    stop_event = _register_stream(camera_id)
    
    async def _task():
        try:
            await process_video_task(
                source=stream_url,
                camera_id=camera_id,
                video_id=None,
                frame_skip=30,
                stop_event=stop_event,
            )
        except Exception as e:
            print(f"❌ Camera {camera_id} background task error: {e}")
        finally:
            _unregister_stream(camera_id)

    # Use asyncio.create_task instead of FastAPI BackgroundTasks to ensure 
    # it runs fully concurrently and doesn't starve the Starlette worker pool
    asyncio.create_task(_task())
    return {"status": "success", "camera_id": camera_id, "message": "Prediction started"}

# ─── Live Data API (Optional) ─────────────────────────────────────────────────

@router.get("/live-data/{camera_id}")
async def live_data(camera_id: str):
    """Returns the absolute newest detection box data from the stream manager (memory), for frontend clickable boxes."""
    return {"camera_id": camera_id, "detections": stream_manager.get_detections(camera_id)}
