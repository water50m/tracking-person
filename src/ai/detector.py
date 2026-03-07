import cv2
from ultralytics import YOLO
import torch  # <--- 1. เพิ่มบรรทัดนี้

class PersonDetector:
    def __init__(self, model_path='yolov8n.pt'):
        # 2. เช็คว่ามี GPU ไหม?
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"🚀 Person Detector using device: {self.device.upper()}")

        # 3. โหลดโมเดลแล้วส่งไปที่ Device นั้น
        self.model = YOLO(model_path)
        self.model.to(self.device)  # <--- คำสั่งสำคัญ! ย้ายไป GPU

    def track_people(self, frame):
        # 4. ส่ง device=self.device เข้าไปเพื่อความชัวร์
        results = self.model.track(
            frame, 
            persist=True, 
            classes=[0], 
            verbose=False,
            device=self.device,      # <--- เพิ่มตรงนี้
            imgsz=320,               # <--- ลดขนาดภาพให้ AI คิดเร็วขึ้น 3-4 เท่า 
            tracker="bytetrack.yaml" # <--- ใช้ Tracker แบบเบา (ไม่ต้องคำนวณ ReID)
        )
        return results[0]