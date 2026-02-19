from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse
import shutil
import os
from typing import Optional, List
from src.services.ai_processor import process_video_task
from src.services.database import DatabaseService
from src.api.schemas import DetectionResponse

router = APIRouter()

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
    label: Optional[str] = Form(None)
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
        background_tasks.add_task(process_video_task, source=file_path, camera_id=camera_id, video_id=str(video_id) if video_id else None)
        
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
    stream_url: str = Form(...) # RTSP Link หรือ "0" สำหรับ Webcam
):
    # สำหรับ Stream ไม่ต้องโหลดไฟล์ ส่ง URL ไปให้ process เลย
    background_tasks.add_task(process_video_task, source=stream_url, camera_id=camera_id, video_id=None)
    
    return {
        "status": "stream_connected",
        "camera_id": camera_id,
        "source": stream_url
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
        
        # Build query
        query = """
            SELECT id, track_id, timestamp, image_path, clothing_category, 
                   class_name, color_profile, camera_id 
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
            minio_base = "http://127.0.0.1:9000/cctv-analysis"
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
                    camera_id=str(row[7]) if row[7] else "N/A"
                ))
            
            return results
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/videos")
async def get_videos():
    """
    ดึงข้อมูลวิดีโอทั้งหมด
    """
    try:
        db = DatabaseService()
        
        query = """
            SELECT id, camera_id, label, filename, file_path, status, created_at 
            FROM processed_videos 
            ORDER BY created_at DESC
        """
        
        with db.conn.cursor() as cur:
            cur.execute(query)
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
                raise HTTPException(
                    status_code=404,
                    detail={
                        "message": "Video file not found",
                        "file_path": file_path,
                        "resolved_path": resolved_path,
                        "tried": candidates,
                    },
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
