from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse
import asyncio
import shutil
import os
import re
from typing import Optional, List
from src.services.ai_processor import process_video_task
from src.services.database import DatabaseService
from src.api.schemas import DetectionResponse
import yt_dlp

router = APIRouter()

# ─── Active stream registry ────────────────────────────────────
# camera_id → asyncio.Event  (set the event to request stop)
_ACTIVE_STREAMS: dict[str, asyncio.Event] = {}


def _register_stream(camera_id: str) -> asyncio.Event:
    """Register a new active stream, raising 409 if already running."""
    if camera_id in _ACTIVE_STREAMS:
        raise HTTPException(
            status_code=409,
            detail=f"Camera '{camera_id}' already has an active processing task. Stop it first.",
        )
    event = asyncio.Event()
    _ACTIVE_STREAMS[camera_id] = event
    return event


def _unregister_stream(camera_id: str) -> None:
    _ACTIVE_STREAMS.pop(camera_id, None)


@router.get("/active-streams")
async def list_active_streams():
    """Return camera IDs that are currently being processed."""
    return {"active": list(_ACTIVE_STREAMS.keys())}


@router.post("/stop/{camera_id}")
async def stop_stream(camera_id: str):
    """Signal an active processing task to stop gracefully."""
    event = _ACTIVE_STREAMS.get(camera_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"No active task for camera '{camera_id}'")
    event.set()
    return {"status": "stop_requested", "camera_id": camera_id}


# สร้างโฟลเดอร์เก็บไฟล์ชั่วคราว
UPLOAD_DIR = "temp_videos"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/analyze/upload")
async def upload_video(
    # 1. BackgroundTasks: 
    # ใช้สำหรับสั่งให้โค้ดทำงานเบื้องหลัง (เช่น การรัน AI ประมวลผลวิดีโอ) 
    # หลังจากที่ API ส่ง Response กลับไปหาหน้าบ้านแล้ว เพื่อไม่ให้หน้าบ้านต้องรอจน AI รันเสร็จ
    background_tasks: BackgroundTasks,

    # 2. camera_id: 
    # รหัสประจำตัวของกล้อง (ID) รับค่าเป็น String 
    # Form(...) หมายความว่าเป็นค่าที่ "จำเป็นต้องส่งมา" (Required) ผ่าน Body แบบ Form-data
    camera_id: str = Form(...),

    # 3. file: 
    # ไฟล์วิดีโอที่ถูกอัปโหลดขึ้นมา (Binary File)
    # UploadFile เป็น Class ของ FastAPI ที่จัดการเรื่องการเก็บไฟล์ลง Memory/Disk ชั่วคราวให้อัตโนมัติ
    # File(...) หมายความว่าเป็น "ไฟล์ที่จำเป็นต้องอัปโหลด" (Required)
    file: UploadFile = File(...),

    # 4. label: 
    # ชื่อเรียกของกล้องแบบที่มนุษย์เข้าใจง่าย (Display Name) เช่น "หน้าประตู", "ลานจอดรถ"
    # Optional[str] หมายถึง "จะส่งมาหรือไม่ส่งก็ได้" (ไม่ได้บังคับ)
    # Form(None) คือค่าตั้งต้นจะเป็น None ถ้าหน้าบ้านไม่ได้ส่งค่านี้มา
    label: Optional[str] = Form(None),
    frame_skip: int = Form(30, description="Process every N-th frame (default: 30)")
):
    try:
        
        # 1. บันทึกไฟล์ลง Disk ก่อน
        file_path = os.path.abspath(os.path.join(UPLOAD_DIR, f"{camera_id}_{file.filename}"))
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 1.5 Register video in database
        db = DatabaseService()
        video_id = db.register_video(
            camera_id=camera_id,
            label=label or camera_id,
            filename=file.filename,
            file_path=file_path
        )
        
        # 2. ส่งงานให้ ai_processor ทำต่อใน Background (โยนงานแล้วจบเลย)
        background_tasks.add_task(process_video_task, source=file_path, camera_id=camera_id, video_id=str(video_id) if video_id else None, frame_skip=frame_skip)
        
        return {
            "status": "processing_started",
            "message": "Video received. AI is processing in the background.",
            "camera_id": camera_id,
            "file_path": file_path,
            "video_id": str(video_id) if video_id else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analyze/stream")
async def stream_video(
    background_tasks: BackgroundTasks,
    camera_id: str = Form(...),
    stream_url: str = Form(...),
    frame_skip: int = Form(30, description="Process every N-th frame (default: 30)")
):
    stop_event = _register_stream(camera_id)  # raises 409 if duplicate

    async def _task():
        try:
            await process_video_task(
                source=stream_url,
                camera_id=camera_id,
                video_id=None,
                frame_skip=frame_skip,
                stop_event=stop_event,
            )
        finally:
            _unregister_stream(camera_id)

    background_tasks.add_task(_task)
    return {
        "status": "stream_connected",
        "camera_id": camera_id,
        "source": stream_url,
    }


YOUTUBE_PATTERN = re.compile(
    r"(https?://)?(www\.)?(youtube\.com/(watch\?v=|shorts/)|youtu\.be/)[A-Za-z0-9_\-]+"
)


def _extract_youtube_stream(url: str) -> dict:
    """Use yt-dlp to get the best direct video stream URL (no downloads)."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        # Avoid m3u8 if possible because OpenCV's libavformat doesn't like jumping between Google's adaptive hosts
        "format": "best[ext=mp4]/best",
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            raise ValueError("Could not extract video info from YouTube URL")
        
        # Check if it's a live stream
        is_live = info.get("is_live", False)
        
        # For merged format the url is in 'url', for adaptive it's in 'requested_downloads'
        stream_url = info.get("url") or (
            info["requested_downloads"][0]["url"] if info.get("requested_downloads") else None
        )
        if not stream_url:
            # Try first format that has a url
            formats = info.get("formats", [])
            valid_formats = [f for f in formats if f.get("url")]
            if valid_formats:
                stream_url = valid_formats[-1]["url"]  # last = usually highest quality
        if not stream_url:
            raise ValueError("No streamable URL found for this video")
        return {
            "stream_url": stream_url,
            "title": info.get("title", url),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
        }


@router.post("/analyze/youtube")
async def analyze_youtube(
    youtube_url: str = Form(...),
    camera_id: str = Form(...),
    label: Optional[str] = Form(None),
    frame_skip: int = Form(30),
):
    """Download + analyse a YouTube video via yt-dlp. (Registers ONLY)."""
    if not YOUTUBE_PATTERN.search(youtube_url):
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")

    try:
        info = _extract_youtube_stream(youtube_url)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"yt-dlp error: {e}")

    # Register in DB
    db = DatabaseService()
    video_id = db.register_video(
        camera_id=camera_id,
        label=label or info["title"],
        filename=info["title"],
        file_path=youtube_url,
    )

    # Upsert into cameras table to make it visible on the dashboard
    try:
        with db.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO cameras (id, name, source_url, is_active) 
                VALUES (%s, %s, %s, true)
                ON CONFLICT (id) DO UPDATE 
                SET name = EXCLUDED.name, source_url = EXCLUDED.source_url, is_active = true
            """, (camera_id, label or info["title"], info["stream_url"]))
            db.conn.commit()
    except Exception as e:
        print(f"Warning: Could not upsert camera to table: {e}")

    return {
        "status": "queued",
        "video_id": video_id,
        "camera_id": camera_id,
        "source": info["stream_url"],
        "title": info["title"],
        "duration": info["duration"],
        "thumbnail": info["thumbnail"],
    }

# --- API endpoints สำหรับลบข้อมูล (สำหรับทดสอบ) ---

@router.delete("/clear")
async def clear_data(type: str = "all"):
    """
    ลบข้อมูลในฐานข้อมูล (สำหรับทดสอบ)
    type: "all", "detections", "videos"
    """
    db = DatabaseService()
    
    try:
        with db.conn.cursor() as cur:
            deleted_detections = 0
            deleted_videos = 0
            
            if type == "all":
                # ลบข้อมูล detections ก่อน
                cur.execute("DELETE FROM detections")
                deleted_detections = cur.rowcount
                
                # ลบข้อมูล processed_videos
                cur.execute("DELETE FROM processed_videos") 
                deleted_videos = cur.rowcount
                
                db.conn.commit()
                
                return {
                    "status": "success",
                    "message": "All data cleared successfully",
                    "deleted_detections": deleted_detections,
                    "deleted_videos": deleted_videos
                }
                
            elif type == "detections":
                cur.execute("DELETE FROM detections")
                deleted_detections = cur.rowcount
                db.conn.commit()
                
                return {
                    "status": "success", 
                    "message": "All detections cleared",
                    "deleted_count": deleted_detections
                }
                
            elif type == "videos":
                cur.execute("DELETE FROM processed_videos")
                deleted_videos = cur.rowcount
                db.conn.commit()
                
                return {
                    "status": "success",
                    "message": "All videos cleared", 
                    "deleted_count": deleted_videos
                }
                
            else:
                raise HTTPException(
                    status_code=400, 
                    detail="Invalid type. Use: all, detections, or videos"
                )
                
    except Exception as e:
        db.conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# --- API endpoints สำหรับดึงข้อมูล ---

@router.get("/detections", response_model=List[DetectionResponse])
async def get_detections(
    limit: int = Query(20, description="Limit number of results"),
    offset: int = Query(0, description="Offset for pagination"),
    camera_id: Optional[str] = Query(None, description="Filter by camera ID"),
    video_id: Optional[str] = Query(None, description="Filter by video ID")
):
    """
    ดึงข้อมูล detection พร้อม filter ตาม camera_id, limit, offset
    """
    try:
        db = DatabaseService()
        
        query = """
            SELECT id, track_id, timestamp, image_path, clothing_category, 
                   class_name, color_profile, camera_id, video_id::text
            FROM detections 
            WHERE 1=1
        """
        params = []
        
        if camera_id:
            query += " AND camera_id = %s"
            params.append(camera_id)
            
        if video_id:
            query += " AND video_id = %s"
            params.append(video_id)
        
        query += " ORDER BY timestamp DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        with db.conn.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
            
            # Map to DetectionResponse format
            minio_base = os.getenv("MINIO_BASE_URL", "http://myserver:9000")
            results = []
            for row in rows:
                results.append(DetectionResponse(
                    id=str(row[0]),
                    track_id=int(row[1]),
                    timestamp=row[2],
                    image_url=f"{minio_base}/{row[3]}" if row[3] else None,
                    category=str(row[4]) if row[4] else "UNKNOWN",
                    class_name=str(row[5]) if row[5] else "unknown",
                    color_profile=row[6] if row[6] else {},
                    camera_id=str(row[7]) if row[7] else "N/A",
                    video_id=str(row[8]) if row[8] else None,
                ))
                # Log the generated URL for debugging
            
            return results
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/videos")
async def get_videos(
    camera_id: Optional[str] = Query(None, description="Filter by camera ID")
):
    """
    ดึงข้อมูลวิดีโอทั้งหมด (กรองตาม camera_id ได้)
    """
    try:
        db = DatabaseService()
        
        query = """
            SELECT id, camera_id, label, filename, file_path, status, created_at 
            FROM processed_videos 
            WHERE 1=1
        """
        params = []
        
        if camera_id:
            query += " AND camera_id = %s"
            params.append(camera_id)
        
        query += " ORDER BY created_at DESC"
        
        with db.conn.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
            
            results = []
            for row in rows:
                results.append({
                    "id": str(row[0]),
                    "camera_id": str(row[1]),
                    "label": str(row[2]),
                    "filename": str(row[3]),
                    "file_path": str(row[4]),
                    "status": str(row[5]),
                    "created_at": row[6]
                })
            
            return results
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/videos/{video_id}/stream")
async def stream_video_file(video_id: str):
    """
    Stream video file for playback
    """
    try:
        db = DatabaseService()
        
        # Get video file path from database
        query = "SELECT file_path, filename FROM processed_videos WHERE id::text = %s"
        
        with db.conn.cursor() as cur:
            cur.execute(query, (video_id,))
            result = cur.fetchone()
            
            if not result:
                raise HTTPException(status_code=404, detail="Video not found")
            
            file_path, filename = result
            file_path = os.path.normpath(str(file_path))
            resolved_path = file_path
            candidates = []
            if not os.path.isabs(resolved_path):
                project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
                candidates = [
                    os.path.normpath(os.path.join(project_root, resolved_path)),
                    os.path.normpath(os.path.join(project_root, UPLOAD_DIR, os.path.basename(resolved_path))),
                ]
                for candidate in candidates:
                    if os.path.exists(candidate):
                        resolved_path = candidate
                        break
            
            # Check if file exists
            if not os.path.exists(resolved_path):
                error_msg = f"Video file not found. Path: {file_path}, Resolved: {resolved_path}, Tried: {candidates}"
                raise HTTPException(
                    status_code=404,
                    detail=error_msg
                )
            
            # Return video file for streaming
            return FileResponse(
                path=resolved_path,
                filename=filename,
                media_type="video/mp4"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
