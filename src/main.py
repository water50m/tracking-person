import cv2
import time
import numpy as np
from datetime import datetime
import threading
import queue

# Import ของที่คุณเขียนไว้
from src.services import DatabaseService, StorageService
from src.ai import PersonDetector, ClothingClassifier, analyze_color_histogram

# 1. ตั้งค่า Queue สำหรับส่งงานไปทำเบื้องหลัง
task_queue = queue.Queue(maxsize=20)
CAMERA_NAME = "CAM-01-FrontDoor"

def bg_worker():
    """ Thread สำหรับทำงานหนัก: AI Predict + MinIO + Database """
    print("👷 Worker Thread: Started and ready.")
    
    # โหลด Service ภายใน Thread (ป้องกันปัญหา Thread-safe)
    db = DatabaseService()
    storage = StorageService()
    classifier = ClothingClassifier()

    while True:
        task = task_queue.get()
        if task is None: break
        
        # ดึงข้อมูลจากคิว
        track_id, person_img, top_crop, bottom_crop = task
        
        try:
            # A. ทายประเภทชุด
            cloth_class, conf = classifier.predict(person_img)
            
            # B. แยก Category และวิเคราะห์สี
            category = "UNKNOWN"
            if cloth_class in ["Dress", "Robe"]:
                category = "FULL"
                color_profile = analyze_color_histogram(person_img)
            elif cloth_class in ["Jeans", "Shorts", "Skirt"]:
                category = "BOTTOM"
                color_profile = analyze_color_histogram(bottom_crop)
            else:
                category = "TOP"
                color_profile = analyze_color_histogram(top_crop)

            # C. อัปโหลดรูปขึ้น MinIO
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp_str}_id{track_id}.jpg"
            image_path = storage.upload_image(person_img, filename)

            # D. บันทึกลง Database
            if image_path:
                db.insert_detection(
                    track_id=track_id,
                    image_path=image_path,
                    category=category,
                    class_name=cloth_class,
                    color_profile=color_profile,
                    camera_id=CAMERA_NAME
                )
                print(f"✅ Background Saved: ID {track_id} | {cloth_class}")

        except Exception as e:
            print(f"❌ Worker Error: {e}")
        
        task_queue.task_done()

def main():
    # เริ่มต้น Thread เบื้องหลัง
    worker = threading.Thread(target=bg_worker, daemon=True)
    worker.start()

    detector = PersonDetector()
    video_source = 0 
    cap = cv2.VideoCapture(video_source)
    
    track_history = {} # เก็บเวลาล่าสุดที่ส่งงานเข้าคิว

    print(f"📷 Camera opened: {video_source} (Smooth Mode Active)")

    while cap.isOpened():
        success, frame = cap.read()
        if not success: break

        # 1. ให้ YOLO หาคน (ทำงานบน GPU ใน Loop หลักเพื่อให้กรอบไม่ดีเลย์)
        results = detector.track_people(frame)

        if results and results.boxes:
            for box in results.boxes:
                if box.id is None: continue
                track_id = int(box.id.item())
                confidence = float(box.conf.item())

                # --- กรองเบื้องต้น (เหมือนเดิม) ---
                if confidence < 0.6: continue
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                w, h = x2 - x1, y2 - y1
                if h < 100 or (h / w) < 1.2: continue

                # วาดกรอบบนจอทันที (สีเขียวคือกำลัง Track)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f"ID:{track_id}", (x1, y1-10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                # --- ตรวจสอบเวลา (กันส่งงานซ้ำรัวๆ) ---
                current_time = time.time()
                last_task_time = track_history.get(track_id, 0)
                
                # ถ้าห่างจากครั้งล่าสุด 3 วินาที และคิวไม่เต็ม ให้ส่งงาน
                if (current_time - last_task_time > 3.0) and not task_queue.full():
                    
                    # ตัดรูป (ต้อง .copy() เพื่อไม่ให้พังเมื่อ frame เปลี่ยน)
                    person_img = frame[y1:y2, x1:x2].copy()
                    if person_img.size > 0:
                        ph, pw, _ = person_img.shape
                        top_crop = person_img[int(ph*0.15):int(ph*0.50), :].copy()
                        bottom_crop = person_img[int(ph*0.50):int(ph*0.90), :].copy()

                        # 🚛 ส่งงานเข้าคิว Worker Thread
                        task_queue.put((track_id, person_img, top_crop, bottom_crop))
                        track_history[track_id] = current_time
                        
                        # วาดกรอบสีแดงทับ (แสดงว่าส่งไปวิเคราะห์แล้ว)
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)

        # แสดงผล (ลื่นแน่นอนเพราะไม่ต้องรอ AI ทายชุด)
        cv2.imshow("CCTV Analytics AI (Threading)", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break

    cap.release()
    cv2.destroyAllWindows()
    print("👋 System Shutdown.")

if __name__ == "__main__":
    main()