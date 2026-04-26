import psycopg2
from psycopg2.extras import Json
import os
from dotenv import load_dotenv

load_dotenv()

class DatabaseService:
    def __init__(self):
        self.conn = None
        self.connect()

    def connect(self):
        try:
            self.conn = psycopg2.connect(
                host=os.getenv("DB_HOST"),
                port=os.getenv("DB_PORT"),
                database=os.getenv("DB_NAME"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASS")
            )
            self.conn.autocommit = True
            print("✅ Database Connected!")
            self.setup_tables()
        except Exception as e:
            print(f"\n❌ FATAL ERROR: Database Connection Failed")
            print(f"   Error Details: {e}")
            print("   👉 คำแนะนำ: เช็คไฟล์ .env อีกครั้ง (User, Password, Database Name)\n")
            self.conn = None

    def _ensure_connection(self):
        """ตรวจสอบและเชื่อมต่อ database ใหม่ถ้าจำเป็น"""
        if self.conn is None or self.conn.closed:
            self.connect()

    def setup_tables(self):
        if self.conn is None:
            return
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS detections (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        track_id INT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        image_path TEXT,
                        clothing_category VARCHAR(50),
                        class_name VARCHAR(100),
                        color_profile JSONB,
                        camera_id VARCHAR(50)
                    );
                    CREATE INDEX IF NOT EXISTS idx_color_profile ON detections USING gin (color_profile);
                    
                    CREATE TABLE IF NOT EXISTS processed_videos (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        camera_id VARCHAR(50),
                        label VARCHAR(100),
                        filename VARCHAR(255),
                        file_path TEXT,
                        status VARCHAR(20) DEFAULT 'processing',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("ALTER TABLE detections ADD COLUMN IF NOT EXISTS video_time_offset DOUBLE PRECISION;")
                cur.execute("ALTER TABLE detections ADD COLUMN IF NOT EXISTS video_id TEXT;")
                try:
                    cur.execute("ALTER TABLE detections ALTER COLUMN video_id TYPE TEXT USING video_id::text;")
                except Exception:
                    pass
                
                # เพิ่มคอลัมน์สำหรับระบบสีใหม่
                cur.execute("ALTER TABLE detections ADD COLUMN IF NOT EXISTS detailed_colors JSONB;")
                cur.execute("ALTER TABLE detections ADD COLUMN IF NOT EXISTS color_groups JSONB;")
                cur.execute("ALTER TABLE detections ADD COLUMN IF NOT EXISTS primary_detailed_color VARCHAR(50);")
                cur.execute("ALTER TABLE detections ADD COLUMN IF NOT EXISTS primary_color_group VARCHAR(50);")
                cur.execute("ALTER TABLE detections ADD COLUMN IF NOT EXISTS clothes JSONB;")
                cur.execute("ALTER TABLE detections ADD COLUMN IF NOT EXISTS bbox JSONB;")
                
                # สร้าง index สำหรับการค้นหาสี
                cur.execute("CREATE INDEX IF NOT EXISTS idx_detailed_colors ON detections USING gin (detailed_colors);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_color_groups ON detections USING gin (color_groups);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_primary_detailed_color ON detections (primary_detailed_color);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_primary_color_group ON detections (primary_color_group);")
        except Exception as e:
            print(f"❌ Setup Tables Failed: {e}")
    
    def register_video(self, camera_id: str, label: str, filename: str, file_path: str):
        query = """
            INSERT INTO processed_videos (camera_id, label, filename, file_path, status)
            VALUES (%s, %s, %s, %s, 'processing')
            RETURNING id;
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (camera_id, label, filename, file_path))
                video_id = cur.fetchone()[0]
                self.conn.commit()
                print(f"🎬 Video registered in DB with ID: {video_id}")
                return video_id
        except Exception as e:
            self.conn.rollback()
            print(f"❌ Error registering video: {e}")
            return None

    def update_video_status(self, video_id, status: str):
        query = "UPDATE processed_videos SET status = %s WHERE id = %s"
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (status, video_id))
                self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            print(f"❌ Error updating video status: {e}")

    def insert_detection(self, *, camera_id, track_id, class_name, color_profile=None, image_path, category=None, video_time_offset=None, video_id=None, detailed_colors=None, color_groups=None, primary_detailed_color=None, primary_color_group=None, clothes=None, bbox=None):
        """
        บันทึกการตรวจจับ โดยรองรับระบบสีละเอียดใหม่
        """
        query = """
            INSERT INTO detections (
                camera_id, track_id, clothing_category, class_name, color_profile,
                detailed_colors, color_groups, primary_detailed_color, primary_color_group,
                clothes, bbox, image_path, video_time_offset, video_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (
                    camera_id, track_id, category, class_name,
                    Json(color_profile if color_profile is not None else {}),
                    Json(detailed_colors if detailed_colors is not None else {}),
                    Json(color_groups if color_groups is not None else {}),
                    primary_detailed_color,
                    primary_color_group,
                    Json(clothes if clothes is not None else []),
                    Json(bbox) if bbox else None,
                    image_path, video_time_offset, video_id,
                ))
                self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            print(f"❌ Database Insert Error: {e}")

    def close(self):
        if self.conn:
            self.conn.close()

    def search_by_detailed_color(self, color_name, limit=100):
        """ค้นหาคนตามสีละเอียด"""
        query = """
            SELECT * FROM detections 
            WHERE detailed_colors ? %s
            ORDER BY timestamp DESC
            LIMIT %s
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (color_name, limit))
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            print(f"❌ Search Error: {e}")
            return []

    def search_by_color_group(self, group_name, limit=100):
        """ค้นหาคนตามกลุ่มสี"""
        query = """
            SELECT * FROM detections 
            WHERE color_groups ? %s
            ORDER BY timestamp DESC
            LIMIT %s
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (group_name, limit))
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            print(f"❌ Search Error: {e}")
            return []

    def search_by_clothes(self, clothing_item, limit=100):
        """ค้นหาคนตามเสื้อผ้า"""
        query = """
            SELECT * FROM detections 
            WHERE clothes @> %s::jsonb
            ORDER BY timestamp DESC
            LIMIT %s
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (Json([clothing_item]), limit))
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            print(f"❌ Search Error: {e}")
            return []

if __name__ == "__main__":
    db = DatabaseService()
