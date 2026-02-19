import cv2
import os
import asyncio
from src.ai.detector import PersonDetector       # Class เดิมของคุณ
from src.ai.classifier import ClothingClassifier # Class เดิมของคุณ
from src.services.database import DatabaseService
from src.services.storage import StorageService  # สมมติว่าคุณมี Service สำหรับ MinIO
from src.ai.color_analysis import analyze_color_histogram  # เพิ่ม import ฟังก์ชันวิเคราะห์สี

async def process_video_task(source: str, camera_id: str, video_id: str | None = None):


    print(f"▶️ [Start] Processing video for Camera: {camera_id} (Source: {source})")
    # 1. Setup Models & DB
    detector = PersonDetector()
    classifier = ClothingClassifier()
    db = DatabaseService()
    # storage = StorageService() # ถ้ามี

    cap = None
    try:
        # 2. Open Video (รองรับทั้งไฟล์และ RTSP)
        # ถ้า source เป็นตัวเลข (เช่น "0") ให้แปลงเป็น int เพื่อเปิด Webcam
        video_source = int(source) if source.isdigit() else source
        cap = cv2.VideoCapture(video_source)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if not cap.isOpened():
            print(f"❌ Error: Cannot open video source {source}")
            if video_id:
                db.update_video_status(video_id, "failed")
            return

        # 3. Processing Loop (ลูปเดิมของคุณ)
        frame_count = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            frame_count += 1
            if frame_count % 5 != 0:  # ประมวลผลทุก 5 เฟรม
                continue
            # ตัวอย่าง: ลดภาระโดยการ process ทุกๆ 3 เฟรม (Optional)
            # if frame_count % 3 != 0: continue

            # --- 👇 ใส่ Logic AI เดิมของคุณตรงนี้ 👇 ---
            results = detector.track_people(frame)
            if results and hasattr(results, 'boxes') and results.boxes is not None:
                for box in results.boxes:
                    # Get bounding box coordinates
                    x1, y1, x2, y2 = map(int, box.xyxy[0])

                    # Crop person from frame
                    person_crop = frame[y1:y2, x1:x2]

                    # Use existing predict function to classify clothing
                    clothing_type, confidence = classifier.predict(person_crop)

                    # B. แยก Category และวิเคราะห์สี (เหมือนกับ real-time)
                    category = "UNKNOWN"
                    color_profile = {}

                    if clothing_type in ["Dress", "Robe"]:
                        category = "FULL"
                        color_profile = analyze_color_histogram(person_crop)
                    elif clothing_type in ["Jeans", "Shorts", "Skirt"]:
                        category = "BOTTOM"
                        # ตัดส่วนล่างสำหรับวิเคราะห์สี
                        ph, pw, _ = person_crop.shape
                        bottom_crop = person_crop[int(ph*0.50):int(ph*0.90), :]
                        color_profile = analyze_color_histogram(bottom_crop)
                    else:
                        category = "TOP"
                        # ตัดส่วนบนสำหรับวิเคราะห์สี
                        ph, pw, _ = person_crop.shape
                        top_crop = person_crop[int(ph*0.15):int(ph*0.50), :]
                        color_profile = analyze_color_histogram(top_crop)

                    video_time_offset = frame_count / fps
                    # Save to database
                    db.insert_detection(
                        track_id=frame_count,  # ใช้ frame_count เป็น track_id ชั่วคราว
                        image_path="",  # ยังไม่ได้บันทึกรูป
                        category=category,  # บันทึก category ที่คำนวณแล้ว
                        class_name=clothing_type,
                        color_profile=color_profile,  # บันทึก color_profile ที่วิเคราะห์แล้ว
                        video_time_offset=video_time_offset,
                        camera_id=camera_id,
                        video_id=video_id,
                    )

                    print(f"👤 Person detected - Clothing: {clothing_type} ({category}) (Conf: {confidence:.2f})")
            # ----------------------------------------

            # ⚠️ หมายเหตุ: บน Server จริงเรามักไม่ใช้ cv2.imshow
            # แต่ถ้า Test เครื่องตัวเอง เปิดดูได้ครับ
            # cv2.imshow(f"Cam: {camera_id}", frame)
            # if cv2.waitKey(1) & 0xFF == ord('q'):
            #     break

            # จำลองการทำงาน (ลบได้)
            await asyncio.sleep(0.01)

        # cv2.destroyAllWindows()
        print(f"✅ [Done] Finished processing for {camera_id}")
        if video_id:
            db.update_video_status(video_id, "completed")

    except Exception as e:
        print(f"❌ Error processing video for {camera_id}: {e}")
        if video_id:
            db.update_video_status(video_id, "failed")
        raise
    finally:
        if cap is not None:
            cap.release()