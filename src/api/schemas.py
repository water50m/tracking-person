from pydantic import BaseModel
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from datetime import datetime

# --- 1. สำหรับข้อมูลดิบ (ใช้ใน List และ Response) ---
class DetectionBase(BaseModel):
    track_id: int
    timestamp: datetime
    image_url: Optional[str] = None
    bbox_image_url: Optional[str] = None
    category: str  # TOP, BOTTOM, FULL
    class_name: str
    color_profile: Dict[str, float]
    bbox: Optional[List[int]] = None
    camera_id: Optional[str] = None

class DetectionResponse(DetectionBase):
    id: str # Primary Key จาก Database
    video_id: Optional[str] = None

# --- 2. สำหรับการค้นหา (นี่คือตัวที่ขาดไปครับ) ---
class SearchCriteria(BaseModel):
    class_names: Optional[List[str]] = None
    class_logic: str = "OR"
    
    color_names: Optional[List[str]] = None
    color_logic: str = "OR"
    
    # ✅ เพิ่มตัวนี้: เกณฑ์ความเข้มข้นของสี (Default 15% คือยอมรับเงา/แสงได้เยอะ)
    # ถ้าตั้ง 10-15% จะจับ "แดงมืดๆ" หรือ "แดงซีดๆ" ได้
    # ถ้าตั้ง 50% จะจับเฉพาะ "แดงสด" เท่านั้น
    color_threshold: float = Field(default=15.0, ge=0.0, le=100.0)
    
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    camera_id: Optional[str] = None
    limit: int = 50
    offset: int = 0

# --- 3. สำหรับการวิเคราะห์และสถิติ ---
class PersonTimeline(BaseModel):
    track_id: int
    first_seen: datetime
    last_seen: datetime
    total_detections: int
    history: List[DetectionResponse]

class DailyStats(BaseModel):
    hour: int
    count: int

class ClothingStats(BaseModel):
    label: str
    count: int

class SearchCriteria(BaseModel):
    # เปลี่ยนเป็น List เพื่อรองรับหลาย Class (เสื้อ หรือ กางเกง)
    class_names: Optional[List[str]] = None 
    
    # เปลี่ยนเป็น List เพื่อรองรับหลายสี (แดง หรือ ส้ม)
    color_names: Optional[List[str]] = None
    
    # เพิ่ม Logic ว่าจะให้สีเป็น AND หรือ OR (Default คือ OR = อันไหนก็ได้)
    color_logic: str = "OR" # ค่าที่เป็นไปได้: "AND", "OR"
    
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    camera_id: Optional[str] = None
    limit: int = 50
    offset: int = 0