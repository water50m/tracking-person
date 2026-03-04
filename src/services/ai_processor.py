import cv2
import os
import asyncio
import uuid
import time
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from src.ai.detector import PersonDetector
from src.ai.classifier import ClothingClassifier
from src.services.database import DatabaseService
from src.services.storage import StorageService
from src.ai.color_analysis import analyze_color_histogram
from src.services.stream_manager import stream_manager

# Thread pool สำหรับ I/O งาน upload (ใช้ร่วมกันทั้ง module)
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="upload")

async def process_video_task(
    source: str,
    camera_id: str,
    video_id: str | None = None,
    frame_skip: int = 30,
    stop_event: asyncio.Event | None = None,
):


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
        
        # เพิ่ม Options ให้ FFmpeg (OpenCV backend) ดึง m3u8 จาก YouTube ได้โดยไม่ตัด connection
        # แก้ปัญหา: Cannot reuse HTTP connection for different host ด้วย http_persistent;0 
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "http_persistent;0|reconnect;1|reconnect_at_eof;1|reconnect_streamed;1|reconnect_delay_max;2|multiple_requests;1"
        
        cap = cv2.VideoCapture(video_source)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if not cap.isOpened():
            print(f"❌ Error: Cannot open video source {source}")
            if video_id:
                db.update_video_status(video_id, "failed")
            return

        # 3. Dedicated thread to continuously read frames and prevent buffering lag
        latest_frame_data = {"count": 0, "frame": None, "ret": True}
        frame_lock = threading.Lock()
        capture_running = True

        def _reader_thread():
            count = 0
            while capture_running:
                ret, f = cap.read()
                if not ret:
                    with frame_lock:
                        latest_frame_data["ret"] = False
                    break
                
                count += 1
                with frame_lock:
                    latest_frame_data["count"] = count
                    latest_frame_data["frame"] = f
                
                # Tiny sleep to yield thread if needed
                time.sleep(0.001)

        reader = threading.Thread(target=_reader_thread, daemon=True)
        reader.start()

        # 4. Processing Loop (AI Thread)
        last_processed_count = -1
        pending_detections = []   # สะสม rows สำหรับ batch insert
        
        def _flush_detections():
            """Helper to upload and insert accumulated detections."""
            if not pending_detections:
                return
            tock = _tick("4_upload_wait")
            for row in pending_detections:
                fut = row.pop("upload_future", None)
                obj = row.pop("object_name", None)
                if fut is not None:
                    try:
                        result = fut.result(timeout=10)
                        row["image_path"] = result or ""
                        # if result: print(f"📸 uploaded: {obj}")
                    except Exception as e:
                        row["image_path"] = ""
                        print(f"❌ Upload error {obj}: {e}")
            tock()

            tock = _tick("5_db_batch_insert")
            db.insert_detections_batch(pending_detections)
            tock()
            pending_detections.clear()

        while capture_running:
            # ── Stop signal check ────────────────────────────────
            if stop_event is not None and stop_event.is_set():
                print(f"🛑 [Stop] Camera {camera_id} received stop signal — exiting loop")
                break

            with frame_lock:
                ret = latest_frame_data["ret"]
                frame_count = latest_frame_data["count"]
                frame = latest_frame_data["frame"].copy() if latest_frame_data["frame"] is not None else None

            if not ret:
                break
                
            if frame is None or frame_count == last_processed_count:
                await asyncio.sleep(0.01)
                continue
                
            last_processed_count = frame_count

            # Skip frames logic: we only run detection if the frame_count is roughly a multiple
            # But since we might skip counts in the reader, we just run AI on whatever latest frame we got 
            # if enough time or frames have passed. For simplicity, we just use modulo on the real count.
            if frame_count % frame_skip != 0:
                await asyncio.sleep(0.01)
                continue

            # ── 1. Detection ─────────────────────────────────────────
            # Only run AI prediction if not paused and on correct frame skip
            run_ai = not stream_manager.is_prediction_paused(camera_id) and (frame_count % frame_skip == 0)
            
            # Maintain the current boxes to draw on every frame
            current_boxes = getattr(process_video_task, f"_boxes_{camera_id}", [])
            current_labels = getattr(process_video_task, f"_labels_{camera_id}", [])
            
            if run_ai:
                tock = _tick("1_detect")
                results = detector.track_people(frame)
                tock()
                
                # Update boxes cache
                new_boxes = []
                new_labels = []

                if results and hasattr(results, 'boxes') and results.boxes is not None:
                    for box in results.boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        person_crop = frame[y1:y2, x1:x2]
                        if person_crop.size == 0: continue

                        # ── 2. Classify ──────────────────────────────────
                        tock = _tick("2_classify")
                        clothing_type, confidence = classifier.predict(person_crop)
                        tock()
                        
                        new_boxes.append((x1, y1, x2, y2))
                        new_labels.append(f"{clothing_type} {confidence:.2f}")

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

                # Flush pending detections to DB immediately if there are enough items
                if len(pending_detections) >= 3:
                    _flush_detections()

                # Update the persistent tracking variables for this camera
                setattr(process_video_task, f"_boxes_{camera_id}", new_boxes)
                setattr(process_video_task, f"_labels_{camera_id}", new_labels)

            # Draw bounding boxes from cache so they appear even on skipped frames
            # Draw on a copy if we want the raw frame for other things, but here modifying is fine
            display_frame = frame.copy()
            for (x1, y1, x2, y2), label in zip(current_boxes, current_labels):
                cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
                cv2.putText(display_frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
                
            # Resize to max 720p to save bandwidth for the Stream API
            h, w = display_frame.shape[:2]
            if h > 720:
                scale = 720 / h
                display_frame = cv2.resize(display_frame, (int(w * scale), 720))

            # Encode and send to stream manager natively
            ret2, jpeg = cv2.imencode(".jpg", display_frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ret2:
                stream_manager.update_frame(camera_id, jpeg.tobytes())

            await asyncio.sleep(0.01)

        # ── Flush any remaining detections at the end ────────────────
        _flush_detections()

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
        capture_running = False  # Signal reader thread to stop
        if cap is not None:
            cap.release()
        # Clean up stream manager and static vars to release memory
        stream_manager.clear_camera(camera_id)
        if hasattr(process_video_task, f"_boxes_{camera_id}"):
            delattr(process_video_task, f"_boxes_{camera_id}")
        if hasattr(process_video_task, f"_labels_{camera_id}"):
            delattr(process_video_task, f"_labels_{camera_id}")
