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

    def insert_detection(self, *, camera_id, track_id, class_name, color_profile, image_path, category=None, video_time_offset=None, video_id=None):
        query = """
            INSERT INTO detections (
                camera_id, track_id, clothing_category, class_name, color_profile,
                image_path, video_time_offset, video_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(query, (
                    camera_id, track_id, category, class_name,
                    Json(color_profile if color_profile is not None else {}),
                    image_path, video_time_offset, video_id,
                ))
                self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            print(f"❌ Database Insert Error: {e}")

    def close(self):
        if self.conn:
            self.conn.close()

if __name__ == "__main__":
    db = DatabaseService()
