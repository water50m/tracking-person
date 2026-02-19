from minio import Minio
import os
from dotenv import load_dotenv
import cv2
import io

load_dotenv()

class StorageService:
    def __init__(self):
        self.client = Minio(
            os.getenv("MINIO_ENDPOINT"),
            access_key=os.getenv("MINIO_ACCESS_KEY"),
            secret_key=os.getenv("MINIO_SECRET_KEY"),
            secure=os.getenv("MINIO_SECURE") == 'True'
        )
        self.bucket_name = os.getenv("MINIO_BUCKET")
        self.ensure_bucket_exists()

    def ensure_bucket_exists(self):
        """ตรวจสอบว่ามี Bucket หรือยัง ถ้าไม่มีให้สร้างเลย"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                print(f"✅ Created Bucket: {self.bucket_name}")
            else:
                print(f"✅ Bucket '{self.bucket_name}' exists.")
        except Exception as e:
            print(f"❌ MinIO Connection Failed: {e}")

    def upload_image(self, image_numpy, filename):
        """รับภาพ OpenCV (numpy) -> แปลงเป็นไฟล์ -> อัปโหลดขึ้น MinIO"""
        try:
            # 1. แปลงภาพ numpy เป็น bytes (เหมือนเซฟไฟล์ลง RAM)
            _, img_encoded = cv2.imencode('.jpg', image_numpy)
            img_bytes = io.BytesIO(img_encoded.tobytes())
            
            # 2. อัปโหลด
            self.client.put_object(
                self.bucket_name,
                filename,
                img_bytes,
                length=img_bytes.getbuffer().nbytes,
                content_type="image/jpeg"
            )
            
            # 3. คืนค่า Path เพื่อเอาไปเก็บใน DB
            return f"{self.bucket_name}/{filename}"
            
        except Exception as e:
            print(f"❌ Upload Failed: {e}")
            return None

# ตัวอย่างการเรียกใช้
if __name__ == "__main__":
    storage = StorageService()