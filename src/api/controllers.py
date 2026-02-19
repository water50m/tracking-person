from typing import List, Optional
from src.services.database import DatabaseService
from src.api.schemas import SearchCriteria, DetectionResponse, PersonTimeline, DailyStats, ClothingStats
from datetime import datetime
import cv2
import numpy as np

class DetectionController:
    def __init__(self):
        self.db = DatabaseService()
        # อย่าลืมแก้ IP ให้ตรงกับเครื่อง MinIO ของคุณ
        self.minio_base = "http://127.0.0.1:9000/cctv-analysis" 

    def _get_select_columns(self):
        """ Helper เพื่อให้ SQL Select ข้อมูลลำดับเดียวกันเสมอ """
        return "id, track_id, timestamp, image_path, clothing_category, class_name, color_profile, camera_id"

    def _map_to_schema(self, row) -> DetectionResponse:
        """ แปลงข้อมูลจาก DB Tuple -> Pydantic Model """
        return DetectionResponse(
            id=str(row[0]),          # UUID -> String
            track_id=int(row[1]),
            timestamp=row[2],
            image_url=f"{self.minio_base}/{row[3]}",
            category=str(row[4]) if row[4] else "UNKNOWN",
            class_name=str(row[5]) if row[5] else "unknown",
            color_profile=row[6] if row[6] else {},
            camera_id=str(row[7]) if row[7] else "N/A"
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
        if not clothing and not colors:
            return {"results": [], "total": 0, "page": page, "has_more": False}

        offset = (page - 1) * limit
        params: list[object] = []

        # UI threshold is 0..1. DB stores percentages 0..100
        threshold_pct = max(0.0, min(1.0, threshold)) * 100.0

        base_where = "WHERE 1=1"
        if camera_id:
            base_where += " AND camera_id = %s"
            params.append(camera_id)
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
            color_conditions = []
            for color in criteria.color_names:
                # ✅ ใช้ criteria.color_threshold แทนเลขตายตัว
                # ความหมาย: "ขอแค่มีสีนี้ผสมอยู่เกิน X% ก็เอามาเลย" (ไม่สนว่าจะมืดหรือสว่าง)
                color_conditions.append(f"(color_profile->>%s)::float >= %s")
                params.extend([color, criteria.color_threshold])
            
            joiner = " OR " if criteria.color_logic == "OR" else " AND "
            query += f" AND ({joiner.join(color_conditions)})"
            if criteria.class_logic == "AND":
                # ✅ กรณี AND: ใช้ท่า INTERSECT ที่คุณต้องการ
                # เราจะหา track_id ที่มีครบทุก class ที่ระบุมา
                
                intersect_queries = []
                for cls_name in criteria.class_names:
                    # สร้าง Subquery สำหรับแต่ละ Class
                    intersect_queries.append("SELECT track_id FROM detections WHERE class_name = %s")
                    params.append(cls_name)
                
                # เอา Subquery มาเชื่อมกันด้วยคำว่า " INTERSECT "
                full_intersect_sql = " INTERSECT ".join(intersect_queries)
                
                # เอาไปแปะใน WHERE track_id IN (...)
                query += f" AND track_id IN ({full_intersect_sql})"

            else:
                # ✅ กรณี OR: ใช้ท่า IN (...) แบบเดิม
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
        if not person_id.isdigit():
            raise ValueError("person_id must be numeric track_id")

        track_id = int(person_id)
        with self.db.conn.cursor() as cur:
            cur.execute(
                f"SELECT {self._get_select_columns()} FROM detections WHERE track_id = %s ORDER BY timestamp ASC",
                (track_id,),
            )
            rows = cur.fetchall()

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
            print(f"Error analyzing image: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
        