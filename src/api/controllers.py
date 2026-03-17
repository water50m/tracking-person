from typing import List, Optional
from src.services.database import DatabaseService
from src.api.schemas import SearchCriteria, DetectionResponse, PersonTimeline, DailyStats, ClothingStats
from datetime import datetime
import cv2
import numpy as np
import os

class DetectionController:
    def __init__(self):
        self.db = DatabaseService()
        self.minio_base = os.getenv("MINIO_BASE_URL", "http://myserver:9000")

    def _get_select_columns(self):
        """ Helper เพื่อให้ SQL Select ข้อมูลลำดับเดียวกันเสมอ """
        return "id, track_id, timestamp, image_path, clothing_category, class_name, color_profile, bbox, camera_id"

    def _map_to_schema(self, row) -> DetectionResponse:
        """ แปลงข้อมูลจาก DB Tuple -> Pydantic Model """
        return DetectionResponse(
            id=str(row[0]),          # UUID -> String
            track_id=int(row[1]),
            timestamp=row[2],
            image_url=f"{self.minio_base}/{row[3]}" if row[3] else None,
            category=str(row[4]) if row[4] else "UNKNOWN",
            class_name=str(row[5]) if row[5] else "unknown",
            color_profile=row[6] if row[6] else {},
            bbox=row[7] if row[7] else None,
            camera_id=str(row[8]) if row[8] else "N/A"
        )

    def get_all(self, limit: int, offset: int) -> List[DetectionResponse]:
        query = f"SELECT {self._get_select_columns()} FROM detections ORDER BY timestamp DESC LIMIT %s OFFSET %s"
        with self.db.conn.cursor() as cur:
            cur.execute(query, (limit, offset))
            rows = cur.fetchall()
            return [self._map_to_schema(r) for r in rows]

    def search_persons(
        self,
        *,
        logic: str,
        threshold: float,
        camera_id: str | None,
        video_id: str | None,
        start_time: str | None,
        end_time: str | None,
        page: int,
        limit: int,
        clothing: list[str],
        colors: list[str],
    ):
        if self.db.conn is None:
            raise RuntimeError("Database not connected")
        if logic not in ["OR", "AND"]:
            raise ValueError("Logic must be OR or AND")
        # Strip accidental empty strings (frontend sends clothing[]="" when none selected)
        clothing = [c for c in clothing if c]
        colors = [c for c in colors if c]
        # Allow search if camera_id or video_id narrows scope, even without clothing/colors
        if not clothing and not colors and not camera_id and not video_id:
            return {"results": [], "total": 0, "page": page, "has_more": False}

        offset = (page - 1) * limit
        params: list[object] = []

        # UI threshold is 0..1. DB stores percentages 0..100
        threshold_pct = max(0.0, min(1.0, threshold)) * 100.0

        base_where = "WHERE 1=1"
        if camera_id:
            base_where += " AND camera_id = %s"
            params.append(camera_id)
        if video_id:
            base_where += " AND video_id = %s"
            params.append(video_id)
        if start_time:
            base_where += " AND timestamp >= %s"
            params.append(start_time)
        if end_time:
            base_where += " AND timestamp <= %s"
            params.append(end_time)

        # Clothing filter
        if clothing:
            if logic == "OR":
                placeholders = ",".join(["%s"] * len(clothing))
                base_where += f" AND class_name IN ({placeholders})"
                params.extend(clothing)
            else:
                intersect_queries = []
                for cls in clothing:
                    intersect_queries.append("SELECT track_id FROM detections WHERE class_name = %s")
                    params.append(cls)
                base_where += f" AND track_id IN ({' INTERSECT '.join(intersect_queries)})"

        # Color filter: require each color key >= threshold_pct
        if colors:
            color_conds = []
            for c in colors:
                color_conds.append("(color_profile->>%s)::float >= %s")
                params.extend([c.lower(), threshold_pct])
            joiner = " OR " if logic == "OR" else " AND "
            base_where += f" AND ({joiner.join(color_conds)})"

        with self.db.conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM detections {base_where}", tuple(params))
            total = int(cur.fetchone()[0] or 0)

            cur.execute(
                f"""
                SELECT {self._get_select_columns()}
                FROM detections
                {base_where}
                ORDER BY timestamp DESC
                LIMIT %s OFFSET %s
                """,
                tuple(params + [limit + 1, offset]),
            )
            rows = cur.fetchall()

        has_more = len(rows) > limit
        rows = rows[:limit]

        results = []
        for row in rows:
            det = self._map_to_schema(row)
            results.append(
                {
                    "id": det.id,
                    "thumbnail_url": det.image_url,
                    "camera_id": det.camera_id or "N/A",
                    "camera_name": det.camera_id or "N/A",
                    "timestamp": det.timestamp.isoformat(),
                    "clothing_class": det.class_name,
                    "color": (det.category or "Unknown"),
                    "confidence": 0.9,
                }
            )

        return {"results": results, "total": total, "page": page, "has_more": has_more}

    def search(self, criteria: SearchCriteria) -> List[DetectionResponse]:
        params = []
        
        # เริ่มต้น Query หลัก
        query = f"SELECT {self._get_select_columns()} FROM detections WHERE 1=1"

        # -------------------------------------------------------
        # 🔥 ไฮไลท์: การจัดการ Class Logic (AND / OR)
        # -------------------------------------------------------
        if criteria.class_names and len(criteria.class_names) > 0:
            if criteria.class_logic == "AND":
                # กรณี AND: หา track_id ที่มีครบทุก class ด้วย INTERSECT
                intersect_queries = []
                for cls_name in criteria.class_names:
                    intersect_queries.append("SELECT track_id FROM detections WHERE class_name = %s")
                    params.append(cls_name)
                full_intersect_sql = " INTERSECT ".join(intersect_queries)
                query += f" AND track_id IN ({full_intersect_sql})"
            else:
                # กรณี OR: ใช้ IN (...)
                placeholders = ', '.join(['%s'] * len(criteria.class_names))
                query += f" AND class_name IN ({placeholders})"
                params.extend(criteria.class_names)

        # -------------------------------------------------------
        # จัดการเงื่อนไขอื่นๆ (เหมือนเดิม)
        # -------------------------------------------------------
        if criteria.color_names and len(criteria.color_names) > 0:
            color_conditions = []
            for color in criteria.color_names:
                color_conditions.append(f"(color_profile->>%s)::float > 20.0")
                params.append(color)
            
            joiner = " OR " if criteria.color_logic == "OR" else " AND "
            query += f" AND ({joiner.join(color_conditions)})"

        if criteria.start_time:
            query += " AND timestamp >= %s"
            params.append(criteria.start_time)
        
        if criteria.end_time:
            query += " AND timestamp <= %s"
            params.append(criteria.end_time)

        if criteria.camera_id:
            query += " AND camera_id = %s"
            params.append(criteria.camera_id)

        # จบด้วยการ Sort และ Limit
        query += " ORDER BY timestamp DESC LIMIT %s OFFSET %s"
        params.extend([criteria.limit, criteria.offset])

        with self.db.conn.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
            return [self._map_to_schema(r) for r in rows]

    def get_person_timeline(self, track_id: int) -> PersonTimeline:
        """ ดึงประวัติการเคลื่อนที่ของคนเฉพาะ ID """
        query = f"SELECT {self._get_select_columns()} FROM detections WHERE track_id = %s ORDER BY timestamp ASC"
        with self.db.conn.cursor() as cur:
            cur.execute(query, (track_id,))
            rows = cur.fetchall()
            
            if not rows:
                # กรณีไม่เจอข้อมูลเลย
                return PersonTimeline(
                    track_id=track_id,
                    first_seen=datetime.now(),
                    last_seen=datetime.now(),
                    total_detections=0,
                    history=[]
                )

            history = [self._map_to_schema(r) for r in rows]
            return PersonTimeline(
                track_id=track_id,
                first_seen=history[0].timestamp,
                last_seen=history[-1].timestamp,
                total_detections=len(history),
                history=history
            )

    def trace_person(self, *, person_id: str):
        if self.db.conn is None:
            raise RuntimeError("Database not connected")
        
        # Handle both numeric and string person IDs
        try:
            track_id = int(person_id)
        except ValueError:
            # If it's not numeric, try to find by person_id field
            with self.db.conn.cursor() as cur:
                cur.execute(
                    f"SELECT track_id FROM detections WHERE person_id = %s LIMIT 1",
                    (person_id,),
                )
                result = cur.fetchone()
                if not result:
                    raise LookupError("Person not found")
                track_id = result[0]
        with self.db.conn.cursor() as cur:
            cur.execute(
                f"SELECT {self._get_select_columns()} FROM detections WHERE track_id = %s ORDER BY timestamp ASC",
                (track_id,),
            )
        if not rows:
            raise LookupError("Person not found")

        detections = []
        cameras: list[str] = []
        thumb = None
        for row in rows:
            det = self._map_to_schema(row)
            if thumb is None:
                thumb = det.image_url
            cam = det.camera_id or "N/A"
            cameras.append(cam)
            detections.append(
                {
                    "id": det.id,
                    "camera_id": cam,
                    "camera_name": cam,
                    "timestamp": det.timestamp.isoformat(),
                    "thumbnail_url": det.image_url,
                    "confidence": 0.9,
                    "bounding_box": None,
                }
            )

        return {
            "person_id": person_id,
            "thumbnail_url": thumb,
            "detections": detections,
            "cameras": sorted(list(set(cameras))),
            "attributes": {},
        }

    def get_detection_detail(self, detection_id: str):
        """Get all details of a specific detection by ID"""
        if self.db.conn is None:
            raise RuntimeError("Database not connected")
        
        with self.db.conn.cursor() as cur:
            cur.execute(
                f"SELECT {self._get_select_columns()}, person_id, video_id, video_time_offset FROM detections WHERE id = %s",
                (detection_id,),
            )
            row = cur.fetchone()
            
        if not row:
            raise LookupError("Detection not found")
        
        # Map to extended schema with additional fields
        detection = self._map_to_schema(row)
        
        # Add additional fields
        return {
            **detection.__dict__,
            "person_id": row[9] if len(row) > 9 else None,
            "video_id": row[10] if len(row) > 10 else None,
            "video_time_offset": row[11] if len(row) > 11 else None,
        }

    def get_hourly_stats(self) -> List[DailyStats]:
        query = """
            SELECT EXTRACT(HOUR FROM timestamp) as hr, COUNT(*) 
            FROM detections 
            WHERE timestamp >= CURRENT_DATE 
            GROUP BY hr ORDER BY hr
        """
        with self.db.conn.cursor() as cur:
            cur.execute(query)
            return [DailyStats(hour=int(r[0]), count=r[1]) for r in cur.fetchall()]

    def get_clothing_distribution(self) -> List[ClothingStats]:
        query = "SELECT class_name, COUNT(*) FROM detections GROUP BY class_name"
        with self.db.conn.cursor() as cur:
            cur.execute(query)
            return [ClothingStats(label=r[0], count=r[1]) for r in cur.fetchall()]

    def get_unique_persons_today(self) -> int:
        query = "SELECT COUNT(DISTINCT track_id) FROM detections WHERE timestamp >= CURRENT_DATE"
        with self.db.conn.cursor() as cur:
            cur.execute(query)
            return int(cur.fetchone()[0] or 0)

    def delete_detection(self, detection_id: str) -> bool: # ✅ แก้ Type เป็น str (UUID)
        """ ลบข้อมูลด้วย UUID string """
        query = "DELETE FROM detections WHERE id = %s"
        with self.db.conn.cursor() as cur:
            cur.execute(query, (detection_id,))
            self.db.conn.commit()
            return True
        
    
        
    def analyze_image_for_search(self, image_bytes: bytes):
        """
        รับไฟล์รูป -> วิเคราะห์ -> ส่งคืน Class และ Color
        """
        try:
            # 1. แปลง Bytes เป็น OpenCV Image
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                raise ValueError("Could not decode image")

            # 2. ส่งเข้า Classifier (ตัวเดิมที่คุณมี)
            # สมมติว่า classifier.predict ส่งคืนค่า (class_name, color_name, confidence)
            # คุณอาจต้องปรับบรรทัดนี้ตาม return type จริงของ classifier คุณ
            class_name, color_name = self.classifier.predict(img)

            # 3. จัด Format ผลลัพธ์ส่งกลับ
            return {
                "status": "success",
                "detected_attributes": {
                    "class_name": class_name,  # เช่น "Short_Sleeve_Shirt"
                    "color_name": color_name   # เช่น "Red"
                }
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
        