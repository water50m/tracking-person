from fastapi import FastAPI, HTTPException, Query
from fastapi import UploadFile, File, Form
from src.api.schemas import *
from src.api.controllers import DetectionController
from fastapi.middleware.cors import CORSMiddleware
from src.api.video_controller import router as video_router
from src.api.routes.realtime import router as realtime_router
from src.api.routes.camera_relationships import router as camera_relationships_router
from src.api.routes.cameras_api import router as cameras_api_router
from src.api.routes.relationships_api import router as relationships_api_router

controller = DetectionController()
app = FastAPI(title="CCTV AI Analytics System")

# Setup CORS (ให้ Next.js เรียกได้)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. ลงทะเบียน Router สำหรับรับ Video
app.include_router(video_router, prefix="/api/video", tags=["Video Input"])

# 2. ลงทะเบียน Router สำหรับ Real-time Events
app.include_router(realtime_router, tags=["Real-time Events"])

# 3. ลงทะเบียน Router สำหรับ Camera Relationships
app.include_router(camera_relationships_router, prefix="/api", tags=["Camera Relationships"])

# 4. ลงทะเบียน Router สำหรับ Camera Management
app.include_router(cameras_api_router, prefix="/api", tags=["Camera Management"])

# 5. ลงทะเบียน Router สำหรับ Camera Relationships Management
app.include_router(relationships_api_router, prefix="/api", tags=["Relationships Management"])

# 2. ลงทะเบียน Router เดิม (Search, Stats, etc.)
# (สมมติว่าคุณแยก route ของ detection ไว้ในไฟล์อื่นก็ include มาแบบเดียวกัน)
# แต่ถ้าเขียนรวมใน main ก็เขียนต่อได้เลย เช่น:
controller = DetectionController()

# --- กลุ่มข้อมูลดิบ (Data List) ---
@app.get("/api/detections", response_model=List[DetectionResponse])
async def list_detections(limit: int = 20, offset: int = 0):
    return controller.get_all(limit, offset)

@app.post("/api/search", response_model=List[DetectionResponse])
async def search(criteria: SearchCriteria):
    return controller.search(criteria)

@app.get("/api/search/persons")
async def search_persons(
    logic: str = Query("OR"),
    threshold: float = Query(0.7),
    camera_id: str | None = Query(None),
    video_id: str | None = Query(None),
    start_time: str | None = Query(None),
    end_time: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(24, ge=1, le=100),
    clothing: list[str] = Query(default=[], alias="clothing[]"),
    colors: list[str] = Query(default=[], alias="colors[]"),
):
    try:
        return controller.search_persons(
            logic=logic,
            threshold=threshold,
            camera_id=camera_id,
            video_id=video_id,
            start_time=start_time,
            end_time=end_time,
            page=page,
            limit=limit,
            clothing=clothing,
            colors=colors,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- กลุ่มติดตามรายคน (Tracking) ---
@app.get("/api/person/{track_id}", response_model=PersonTimeline)
async def person_detail(track_id: int):
    result = controller.get_person_timeline(track_id)
    if not result.history:
        raise HTTPException(status_code=404, detail="Track ID not found")
    return result

@app.get("/api/persons/{person_id}/trace")
async def trace_person(person_id: str):
    try:
        return controller.trace_person(person_id=person_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/persons/{person_id}")
async def get_person_by_id(person_id: str):
    """Get person by UUID person_id"""
    try:
        return controller.trace_person(person_id=person_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/detections/{detection_id}")
async def get_detection_detail(detection_id: str):
    """Get all details of a specific detection by ID"""
    try:
        return controller.get_detection_detail(detection_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- กลุ่มสถิติ (Analytics) ---
@app.get("/api/stats/hourly", response_model=List[DailyStats])
async def hourly_metrics():
    return controller.get_hourly_stats()

@app.get("/api/stats/clothing", response_model=List[ClothingStats])
async def clothing_metrics():
    return controller.get_clothing_distribution()

# --- การจัดการข้อมูล ---
@app.delete("/api/detections/{id}")
async def remove_record(id: str): 
    controller.delete_detection(id)
    return {"status": "deleted", "id": id}


@app.get("/api/detections")
async def list_detections(limit: int = 20, offset: int = 0):
    return controller.get_all(limit, offset)



@app.post("/api/search/detect-attributes")
async def detect_attributes_from_image(file: UploadFile = File(...)):
    """
    API สำหรับรับรูปแล้วบอกว่า 'นี่คือชุดอะไร สีอะไร'
    เพื่อให้ Frontend เอาไป Auto-fill ในช่องค้นหา
    """
    image_bytes = await file.read()
    result = controller.analyze_image_for_search(image_bytes)
    return result