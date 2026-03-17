import os
# ตั้งค่า FFmpeg Capture Options ให้โหลดตั้งแต่ก่อนเรียก cv2 
# เพื่อให้แน่ใจว่า C++ backend นำค่าเหล่านี้ไปใช้ในการเปิด Stream (แก้ไขปัญหา HTTP connection ไม่ตรงกัน)
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "http_persistent;0|reconnect;1|reconnect_at_eof;1|reconnect_streamed;1|reconnect_delay_max;5|timeout;10000000|rw_timeout;10000000"

import cv2
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

    import re
    import yt_dlp

    import re
    import yt_dlp

    cap = None
    try:
        # 2. Open Video (รองรับทั้งไฟล์และ RTSP)
        # ถ้า source เป็นตัวเลข (เช่น "0") ให้แปลงเป็น int เพื่อเปิด Webcam
        video_source = int(source) if source.isdigit() else source
        
        # If the source is a YouTube URL, extract the raw m3u8 stream on the fly
        YOUTUBE_PATTERN = re.compile(r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/')
        if isinstance(video_source, str) and YOUTUBE_PATTERN.search(video_source):
            try:
                print(f"[AIProcessor] Resolving YouTube URL: {video_source}")
                ydl_opts = {
                    'format': 'best[ext=mp4]/best',
                    'quiet': True,
                    'no_warnings': True,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(video_source, download=False)
                    video_source = info.get('url', video_source)
                print(f"[AIProcessor] Successfully extracted raw stream URL")
            except Exception as e:
                print(f"❌ Error extracting YouTube stream for AI Processing: {e}")
                if video_id:
                    db.update_video_status(video_id, "failed")
                return
        
        # If the source is a YouTube URL, extract the raw m3u8 stream on the fly
        YOUTUBE_PATTERN = re.compile(r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/')
        if isinstance(video_source, str) and YOUTUBE_PATTERN.search(video_source):
            try:
                print(f"[AIProcessor] Resolving YouTube URL: {video_source}")
                ydl_opts = {
                    'format': 'best[ext=mp4]/best',
                    'quiet': True,
                    'no_warnings': True,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(video_source, download=False)
                    video_source = info.get('url', video_source)
                print(f"[AIProcessor] Successfully extracted raw stream URL")
            except Exception as e:
                print(f"❌ Error extracting YouTube stream for AI Processing: {e}")
                if video_id:
                    db.update_video_status(video_id, "failed")
                return

        # เพิ่ม Options ให้ FFmpeg (OpenCV backend) ดึง m3u8 จาก YouTube ได้โดยไม่ตัด connection
        # ค่าถูกนำไปตั้งไว้ที่บรรทัดบนสุดของไฟล์แล้ว (OPENCV_FFMPEG_CAPTURE_OPTIONS)
        
        cap = cv2.VideoCapture(video_source)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if not cap.isOpened():
            print(f"❌ Error: Cannot open video source {source} (Resolved to: {video_source[:50]}...)")
            if video_id:
                db.update_video_status(video_id, "failed")
            return

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_time = 1.0 / fps

        # --- Resume Logic ---
        start_frame = db.get_video_progress(video_id) if video_id else 0
        
        # Only try to seek if it's > 0 and not a pure Live stream (RTSP/Webcam usually fail silently on seek)
        if start_frame > 0:
            success = cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            if success:
                print(f"▶️ Resuming video {video_id} from frame {start_frame}")
            else:
                print(f"⚠️ Could not seek to frame {start_frame}. Starting from beginning.")
                start_frame = 0

        # --- Resume Logic ---
        start_frame = db.get_video_progress(video_id) if video_id else 0
        
        # Only try to seek if it's > 0 and not a pure Live stream (RTSP/Webcam usually fail silently on seek)
        if start_frame > 0:
            success = cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            if success:
                print(f"▶️ Resuming video {video_id} from frame {start_frame}")
            else:
                print(f"⚠️ Could not seek to frame {start_frame}. Starting from beginning.")
                start_frame = 0

        # 3. Dedicated thread to continuously read frames and prevent buffering lag
        latest_frame_data = {"count": start_frame, "frame": None, "ret": True}
        frame_lock = threading.Lock()
        capture_running = True

        def _reader_thread():
            count = start_frame
            # Track start time to maintain absolute pacing
            stream_start_time = time.perf_counter()
            
            while capture_running:
                if stop_event is not None and stop_event.is_set():
                    break
                ret, f = cap.read()
                if not ret:
                    with frame_lock:
                        latest_frame_data["ret"] = False
                    break
                
                count += 1
                with frame_lock:
                    latest_frame_data["count"] = count
                    latest_frame_data["frame"] = f
                
                # Pace the reader exactly to the stream's FPS to prevent 
                # burst-reading from local files or network buffers like YouTube
                frames_processed_this_session = count - start_frame
                expected_time = stream_start_time + (frames_processed_this_session * frame_time)
                sleep_time = expected_time - time.perf_counter()
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
                # If we lag behind real-time by more than 1 second (e.g. network stall), 
                # reset the baseline so it doesn't try to play catch up at 100x speed
                elif sleep_time < -1.0:
                    stream_start_time = time.perf_counter() - (frames_processed_this_session * frame_time)

        reader = threading.Thread(target=_reader_thread, daemon=True)
        reader.start()

        # 4. Processing Loop (AI Thread)
        last_processed_count = -1
        
        # Dedicated Async Queue for DB inserts to prevent ThreadPool starvation or blocking
        db_queue = asyncio.Queue()
        
        async def _detection_inserter_task():
            """Continuously consumes from the queue and inserts to DB in the background."""
            db_thread = DatabaseService()
            batch = []
            
            while True:
                try:
                    # Wait for items, or timeout to flush a partial batch
                    row = await asyncio.wait_for(db_queue.get(), timeout=2.0)
                    if row is None: # Sentinel to exit
                        break
                        
                    # Resolve upload future if present
                    fut = row.pop("upload_future", None)
                    obj = row.pop("object_name", None)
                    if fut is not None:
                        try:
                            # Use an executor to avoid blocking the insert loop too long
                            loop = asyncio.get_running_loop()
                            result = await loop.run_in_executor(None, fut.result, 10) # 10s timeout
                            row["image_path"] = result or ""
                        except Exception as e:
                            row["image_path"] = ""
                            print(f"❌ Upload error {obj}: {e}")
                            
                    # Resolve bbox upload future if present
                    bbox_fut = row.pop("bbox_upload_future", None)
                    bbox_obj = row.pop("bbox_object_name", None)
                    if bbox_fut is not None:
                        try:
                            loop = asyncio.get_running_loop()
                            bbox_result = await loop.run_in_executor(None, bbox_fut.result, 10) # 10s timeout
                            row["bbox_image_path"] = bbox_result or ""
                        except Exception as e:
                            row["bbox_image_path"] = ""
                            print(f"❌ Bbox upload error {bbox_obj}: {e}")
                            
                    batch.append(row)
                    db_queue.task_done()
                    
                    # Flush batch if large enough
                    if len(batch) >= 5:
                        db_thread.insert_detections_batch(batch)
                        batch.clear()
                        
                except asyncio.TimeoutError:
                    # Flush partial batch on timeout if we have any
                    if batch:
                        db_thread.insert_detections_batch(batch)
                        batch.clear()
                except Exception as e:
                    print(f"❌ Background DB Inserter Error: {e}")
            
            # Final flush on exit
            if batch:
                db_thread.insert_detections_batch(batch)

        # Start the inserter task
        inserter_task = asyncio.create_task(_detection_inserter_task())

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
                
            # Process frames at ~15 FPS for smooth tracking without overwhelming CPU
            # (e.g. if source is 30fps, process every 2nd frame)
            track_skip = max(1, int(fps / 15)) 
            if frame is None or frame_count - last_processed_count < track_skip:
                await asyncio.sleep(0.005)
                continue
                
            last_processed_count = frame_count

            # ── Periodic checkpoint: Save progress every 300 frames ─────────────
            # This ensures that if the server crashes, the startup cleanup in
            # main.py can mark this video as 'paused' with the correct frame
            # number to resume from (rather than starting from 0 again).
            if video_id and last_processed_count % 300 == 0 and last_processed_count > 0:
                db.update_video_progress(video_id, last_processed_count, "processing")

            # ── Periodic checkpoint: Save progress every 300 frames ─────────────
            # This ensures that if the server crashes, the startup cleanup in
            # main.py can mark this video as 'paused' with the correct frame
            # number to resume from (rather than starting from 0 again).
            if video_id and last_processed_count % 300 == 0 and last_processed_count > 0:
                db.update_video_progress(video_id, last_processed_count, "processing")

            # ── 1. Detection (Continuous Background Tracking) ───────────────────
            run_ai = not stream_manager.is_prediction_paused(camera_id)
            
            # Use previously calculated tracking data to draw
            current_boxes = getattr(process_video_task, f"_boxes_{camera_id}", [])
            current_labels = getattr(process_video_task, f"_labels_{camera_id}", [])
            track_labels = getattr(process_video_task, f"_track_labels_{camera_id}", {})
            
            if run_ai:
                # Prevent piling up YOLO tasks if one is already running
                is_inferring = getattr(process_video_task, f"_inferring_{camera_id}", False)
                if not is_inferring:
                    setattr(process_video_task, f"_inferring_{camera_id}", True)
                    
                    # Capture the frame and info asynchronously
                    inference_frame = frame.copy()
                    current_count = frame_count
                    
                    async def _run_tracking_and_classification():
                        try:
                            loop = asyncio.get_running_loop()
                            
                            tock = _tick("1_detect_async")
                            # 1. Run YOLO Tracking (taking ~45ms on CPU)
                            results = await loop.run_in_executor(None, detector.track_people, inference_frame)
                            tock()
                            
                            new_boxes = []
                            new_labels = []
                            run_heavy_classifier = (current_count % frame_skip == 0)
                            boxes_to_classify = []

                            if results and hasattr(results, 'boxes') and results.boxes is not None:
                                for box in results.boxes:
                                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                                    new_boxes.append((x1, y1, x2, y2))
                                    
                                    # Get tracking ID if available
                                    track_id_obj = getattr(box, 'id', None)
                                    person_id = int(track_id_obj[0]) if track_id_obj is not None else None
                                    
                                    # Use cached label or default
                                    label = track_labels.get(person_id, "Person") if person_id else "Person"
                                    new_labels.append(label)
                                    
                                    if run_heavy_classifier:
                                        boxes_to_classify.append({
                                            "coords": (x1, y1, x2, y2),
                                            "person_id": person_id
                                        })

                            # Immediately update the shared boxes so the main stream can draw them on the NEXT frame
                            setattr(process_video_task, f"_boxes_{camera_id}", new_boxes)
                            setattr(process_video_task, f"_labels_{camera_id}", new_labels)

                            # 2. Run Heavy Classification if scheduled
                            if run_heavy_classifier and boxes_to_classify:
                                for bdata in boxes_to_classify:
                                    bx1, by1, bx2, by2 = bdata["coords"]
                                    pid = bdata["person_id"]
                                    person_crop = inference_frame[by1:by2, bx1:bx2]
                                    if person_crop.size == 0: continue

                                    tock = _tick("2_classify_async")
                                    clothing_type, confidence = await loop.run_in_executor(
                                        None, classifier.predict, person_crop
                                    )
                                    tock()
                                    
                                    if pid:
                                        track_labels[pid] = f"{clothing_type} {confidence:.2f}"
                                        setattr(process_video_task, f"_track_labels_{camera_id}", track_labels)

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

                                    video_time_offset = current_count / fps
                                    upload_future = None
                                    object_name   = ""
                                    bbox_object_name = ""
                                    
                                    if storage is not None and person_crop.size != 0:
                                        tock = _tick("4_upload_submit")
                                        object_name = f"detections/{camera_id}/{video_id or 'no-video'}/{current_count}_{uuid.uuid4().hex}.jpg"
                                        crop_copy = person_crop.copy()
                                        upload_future = _EXECUTOR.submit(storage.upload_image, crop_copy, object_name)
                                        
                                        # Also save the frame with bounding box drawn
                                        bbox_frame = display_frame.copy()
                                        # Draw the specific bounding box for this person
                                        cv2.rectangle(bbox_frame, (bx1, by1), (bx2, by2), (0, 255, 255), 2)
                                        label = track_labels.get(pid, f"{clothing_type} {confidence:.2f}")
                                        cv2.putText(bbox_frame, label, (bx1, by1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
                                        
                                        bbox_object_name = f"detections/{camera_id}/{video_id or 'no-video'}/bbox_{current_count}_{uuid.uuid4().hex}.jpg"
                                        bbox_copy = bbox_frame.copy()
                                        bbox_upload_future = _EXECUTOR.submit(storage.upload_image, bbox_copy, bbox_object_name)
                                        tock()

                                    db_queue.put_nowait({
                                        "track_id":          current_count,
                                        "image_path":        "",
                                        "object_name":       object_name,
                                        "upload_future":     upload_future,
                                        "bbox_image_path":   "",
                                        "bbox_object_name":  bbox_object_name,
                                        "bbox_upload_future": bbox_upload_future if 'bbox_upload_future' in locals() else None,
                                        "category":          category,
                                        "class_name":        clothing_type,
                                        "color_profile":     color_profile,
                                        "bbox":              [bx1, by1, bx2, by2],
                                        "bbox":              [bx1, by1, bx2, by2],
                                        "video_time_offset": video_time_offset, 
                                        "camera_id":         camera_id,
                                        "video_id":          video_id,
                                    })

                                    print(f"👤 Person classified: {clothing_type} ({category}) (Conf: {confidence:.2f})")
                                    
                        except Exception as e:
                            print(f"❌ AI pipeline error: {e}")
                        finally:
                            # Flag that we are ready to process a new AI frame
                            setattr(process_video_task, f"_inferring_{camera_id}", False)
                            
                    # Fire and forget the AI cycle so the stream loop can immediately output the frame
                    asyncio.create_task(_run_tracking_and_classification())

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

            # Calculate and draw debug FPS
            now = time.time()
            draw_fps = getattr(process_video_task, f"_fps_time_{camera_id}", now)
            fps_val = 1.0 / (now - draw_fps) if now - draw_fps > 0 else 0
            setattr(process_video_task, f"_fps_time_{camera_id}", now)
            
            # Smooth out FPS display
            avg_fps = getattr(process_video_task, f"_fps_avg_{camera_id}", fps_val)
            avg_fps = (avg_fps * 0.9) + (fps_val * 0.1)
            setattr(process_video_task, f"_fps_avg_{camera_id}", avg_fps)
            
            debug_text = f"Target FPS: {fps:.1f} | Actual Process FPS: {avg_fps:.1f}"
            cv2.putText(display_frame, debug_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            # Encode and send to stream manager natively
            ret2, jpeg = cv2.imencode(".jpg", display_frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ret2:
                stream_manager.update_frame(camera_id, jpeg.tobytes())

            await asyncio.sleep(0.01)

        # ── Flush any remaining detections at the end ────────────────
        db_queue.put_nowait(None)
        try:
            await asyncio.wait_for(inserter_task, timeout=5.0)
        except asyncio.TimeoutError:
            print(f"⚠️ [Timeout] Inserter task for camera {camera_id} taking too long to shutdown.")

        # ── Summary ──────────────────────────────────────────────────
        _print_timing_summary()
        if video_id:
            if stop_event is not None and stop_event.is_set():
                print(f"⏸️ [Paused] Stopping processing for {camera_id} at frame {last_processed_count}")
                db.update_video_progress(video_id, last_processed_count, "paused")
            else:
                print(f"✅ [Done] Finished processing for {camera_id}")
            if stop_event is not None and stop_event.is_set():
                print(f"⏸️ [Paused] Stopping processing for {camera_id} at frame {last_processed_count}")
                db.update_video_progress(video_id, last_processed_count, "paused")
            else:
                print(f"✅ [Done] Finished processing for {camera_id}")
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
