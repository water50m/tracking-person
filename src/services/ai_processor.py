import cv2
import os
import asyncio
import uuid
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from src.ai.detector import PersonDetector
from src.ai.classifier import ClothingClassifier
from src.services.database import DatabaseService
from src.services.storage import StorageService
from src.ai.color_analysis import analyze_color_histogram

# Thread pool สำหรับ I/O งาน upload (ใช้ร่วมกันทั้ง module)
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="upload")

async def process_video_task(source: str, camera_id: str, video_id: str | None = None, frame_skip: int = 30):


    print(f"▶️ [Start] Processing video for Camera: {camera_id} (Source: {source}, frame_skip: every {frame_skip} frames)")
    # 1. Setup Models & DB
    detector = PersonDetector()
    classifier = ClothingClassifier()
    db = DatabaseService()
    storage = None
    try:
        storage = StorageService()
    except Exception as e:
        print(f"⚠️ StorageService unavailable, thumbnails will not be saved: {e}")

    # ── Timing accumulators ──────────────────────────────────────────
    _t = defaultdict(float)   # สะสมเวลารวมของแต่ละ step
    _n = defaultdict(int)     # สะสมจำนวนครั้งที่เรียก

    def _tick(label: str):
        """เริ่มจับเวลา — คืน lambda สำหรับหยุด"""
        t0 = time.perf_counter()
        def _tock():
            _t[label] += time.perf_counter() - t0
            _n[label] += 1
        return _tock

    def _print_timing_summary():
        print("\n" + "─" * 55)
        print(f"⏱️  TIMING SUMMARY  [{camera_id}]")
        print("─" * 55)
        total = sum(_t.values())
        for label, elapsed in sorted(_t.items(), key=lambda x: -x[1]):
            calls = _n[label]
            avg   = elapsed / calls if calls else 0
            pct   = elapsed / total * 100 if total else 0
            print(f"  {label:<20} {elapsed:7.3f}s  avg {avg*1000:6.1f}ms/call  {pct:5.1f}%  (x{calls})")
        print("─" * 55)
        print(f"  {'TOTAL':<20} {total:7.3f}s")
        print("─" * 55 + "\n")
    # ────────────────────────────────────────────────────────────────

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

        # 3. Processing Loop
        frame_count        = 0
        pending_detections = []   # สะสม rows สำหรับ batch insert
        while cap.isOpened():

            ret, frame = cap.read()
            if not ret:
                break
            frame_count += 1
            if frame_count % frame_skip != 0:  # ประมวลผลทุก frame_skip เฟรม
                continue

            # ── 1. Detection ─────────────────────────────────────────
            tock = _tick("1_detect")
            results = detector.track_people(frame)
            tock()

            if results and hasattr(results, 'boxes') and results.boxes is not None:
                for box in results.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    person_crop = frame[y1:y2, x1:x2]

                    # ── 2. Classify ──────────────────────────────────
                    tock = _tick("2_classify")
                    clothing_type, confidence = classifier.predict(person_crop)
                    tock()

                    # ── 3. Color analysis ────────────────────────────
                    tock = _tick("3_color")
                    category = "UNKNOWN"
                    color_profile = {}

                    if clothing_type in ["Dress", "Robe"]:
                        category = "FULL"
                        color_profile = analyze_color_histogram(person_crop)
                    elif clothing_type in ["Jeans", "Shorts", "Skirt"]:
                        category = "BOTTOM"
                        ph, pw, _ = person_crop.shape
                        bottom_crop = person_crop[int(ph*0.50):int(ph*0.90), :]
                        color_profile = analyze_color_histogram(bottom_crop)
                    else:
                        category = "TOP"
                        ph, pw, _ = person_crop.shape
                        top_crop = person_crop[int(ph*0.15):int(ph*0.50), :]
                        color_profile = analyze_color_histogram(top_crop)
                    tock()

                    video_time_offset = frame_count / fps

                    # ── 4. Upload image (async non-blocking) ─────────
                    upload_future = None
                    object_name   = ""
                    if storage is not None and person_crop is not None and person_crop.size != 0:
                        tock = _tick("4_upload_submit")
                        object_name = f"detections/{camera_id}/{video_id or 'no-video'}/{frame_count}_{uuid.uuid4().hex}.jpg"
                        # ส่งงาน upload ไปรันใน thread pool โดยไม่รอผล
                        crop_copy     = person_crop.copy()  # copy ก่อนส่ง thread เพื่อกัน race condition
                        upload_future = _EXECUTOR.submit(storage.upload_image, crop_copy, object_name)
                        tock()

                    # ── 5. สะสม detection row (batch) ────────────────
                    pending_detections.append({
                        "track_id":          frame_count,
                        "image_path":        "",          # จะ fill หลัง upload เสร็จ
                        "object_name":       object_name,
                        "upload_future":     upload_future,
                        "category":          category,
                        "class_name":        clothing_type,
                        "color_profile":     color_profile,
                        "video_time_offset": video_time_offset,
                        "camera_id":         camera_id,
                        "video_id":          video_id,
                    })

                    print(f"👤 Person detected - Clothing: {clothing_type} ({category}) (Conf: {confidence:.2f})")

            await asyncio.sleep(0.01)

        # ── รอ upload ทั้งหมดเสร็จ แล้ว batch insert ────────────────
        tock = _tick("4_upload_wait")
        for row in pending_detections:
            fut = row.pop("upload_future")
            obj = row.pop("object_name")
            if fut is not None:
                try:
                    result = fut.result(timeout=30)
                    row["image_path"] = result or ""
                    if result:
                        print(f"📸 uploaded: {obj} → {result}")
                    else:
                        print(f"❌ Upload failed: {obj}")
                except Exception as e:
                    print(f"❌ Upload error {obj}: {e}")
        tock()

        tock = _tick("5_db_batch_insert")
        db.insert_detections_batch(pending_detections)
        tock()


        # ── Summary ──────────────────────────────────────────────────
        print(f"✅ [Done] Finished processing for {camera_id}")
        _print_timing_summary()
        if video_id:
            db.update_video_status(video_id, "completed")

    except Exception as e:
        print(f"❌ Error processing video for {camera_id}: {e}")
        _print_timing_summary()   # แสดง summary แม้เกิด error
        if video_id:
            db.update_video_status(video_id, "failed")
        raise
    finally:
        if cap is not None:
            cap.release()
