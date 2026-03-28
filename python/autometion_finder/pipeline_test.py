"""
pipeline_test.py — ระบบทดสอบ Detection + DeepSORT Tracking + Clothing Classification

โหมดการใช้งาน (เลือกผ่าน MODE หรือ argument):
  python pipeline_test.py            → โหมด visual (default, เห็น OpenCV window)
  python pipeline_test.py --bg       → โหมด background (ไม่มีหน้าต่าง, save DB)
  python pipeline_test.py --results  → ดูสรุปผลลัพธ์ใน DB
  python pipeline_test.py --phase 1  → เลือก phase (ใช้ร่วมกับ --bg หรือ visual)

Phase:
  1 = detect คนเท่านั้น
  2 = detect + DeepSORT tracking
  3 = detect + DeepSORT + classify clothing + บันทึก DB/รูปภาพ (full)
"""

import sys
import os
import argparse
import time
import cv2
import torch

# ==========================================
# ⚙️ CONFIG — แก้ตรงนี้ได้เลย
# ==========================================
PHASE        = 3
# SOURCE       = r"E:\ALL_CODE\my-project\temp_videos\CAM-01_4p-c0-new.mp4"            # 0 = webcam | path ไฟล์วิดีโอ เช่น "test.mp4"
SOURCE       = "https://www.youtube.com/watch?v=UemFRPrl1hk"  # YouTube live
CAMERA_ID    = "test-cam"   # ID ของกล้อง (ใช้ใน DB)
MODEL_DETECT = "yolo11s.pt"
MODEL_CLOTH  = os.path.join(
    os.path.dirname(__file__), "../../models/clothing_classifier.pt"
)
MIN_BOX_W    = 0    # ปิด filter แล้ว (0 = ไม่กรอง)
MIN_BOX_H    = 0
OUTPUT_DIR   = "pipeline_results"   # โฟลเดอร์เก็บรูป (Phase 3)
CONF_THRESH  = 0.20
FRAME_SKIP   = 2    # process ทุกกี่ frame (1 = ทุก frame, 2 = ข้าม 1, 3 = ข้าม 2 ...)
# ==========================================

# ── Parse arguments
parser = argparse.ArgumentParser(description="Pipeline Test")
parser.add_argument("--bg",      action="store_true", help="รันแบบ background (ไม่มีหน้าต่าง)")
parser.add_argument("--results", action="store_true", help="ดูสรุปผลใน DB แล้วออก")
parser.add_argument("--phase",   type=int, default=PHASE, help="Phase 1/2/3")
parser.add_argument("--tracker", type=str, default="boxmot",
                    choices=["deepsort", "bytetrack", "botsort", "boxmot"],
                    help="Tracking algorithm: deepsort | bytetrack | botsort | boxmot")
parser.add_argument("--debug",   action="store_true",
                    help="แสดง raw detection ทั้งหมดก่อน filter (ช่วย diagnose)")
parser.add_argument("--conf",    type=float, default=CONF_THRESH, help="Confidence threshold (default: 0.20)")
parser.add_argument("--min-w",   type=int,   default=MIN_BOX_W,   help="Min box width px (default: 0)")
parser.add_argument("--min-h",   type=int,   default=MIN_BOX_H,   help="Min box height px (default: 0)")
parser.add_argument("--skip",    type=int,   default=FRAME_SKIP,  help="Process every N frames (default: 2)")
args = parser.parse_args()

PHASE        = args.phase
TRACKER_NAME = args.tracker
SHOW_WINDOW  = not args.bg
CONF_THRESH  = args.conf
MIN_BOX_W    = args.min_w
MIN_BOX_H    = args.min_h
DEBUG        = args.debug
FRAME_SKIP   = max(1, args.skip)

# ── เพิ่ม src root ลง path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ==========================================
# MODE: --results  →  แสดงผลจาก DB แล้วออก
# ==========================================
if args.results:
    print("\n" + "="*55)
    print("  📊 PIPELINE RESULTS — สรุปผลจากฐานข้อมูล")
    print("="*55)
    try:
        from src.services.database import DatabaseService
        db = DatabaseService()
        with db.conn.cursor() as cur:
            # สรุปจำนวนตามประเภทเสื้อผ้า
            cur.execute("""
                SELECT class_name, COUNT(*) as cnt
                FROM detections
                WHERE camera_id = %s
                GROUP BY class_name
                ORDER BY cnt DESC
            """, (CAMERA_ID,))
            rows = cur.fetchall()
            if not rows:
                print(f"\n  ⚠️ ยังไม่มีข้อมูลสำหรับ CAMERA_ID='{CAMERA_ID}'")
            else:
                print(f"\n  Camera: {CAMERA_ID}")
                print(f"  {'Class':<25} {'Count':>6}")
                print(f"  {'-'*33}")
                for cls, cnt in rows:
                    print(f"  {str(cls):<25} {cnt:>6}")

            # 10 รายการล่าสุด
            cur.execute("""
                SELECT track_id, class_name, timestamp, image_path
                FROM detections
                WHERE camera_id = %s
                ORDER BY timestamp DESC
                LIMIT 10
            """, (CAMERA_ID,))
            recent = cur.fetchall()
            if recent:
                print(f"\n  {'ล่าสุด 10 รายการ'}")
                print(f"  {'ID':>6}  {'Class':<22}  {'Time'}")
                print(f"  {'-'*50}")
                for tid, cls, ts, img in recent:
                    print(f"  {str(tid):>6}  {str(cls):<22}  {ts}")
        db.close()
    except Exception as e:
        print(f"\n  ❌ ไม่สามารถเชื่อมต่อ DB: {e}")
        print("     ตรวจสอบไฟล์ .env (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS)")
    print("="*55 + "\n")
    sys.exit(0)


# ==========================================
# DRAWING HELPERS
# ==========================================
COLORS = {
    "bbox":  (0, 220, 60),
    "track": (50, 180, 255),
    "cloth": (255, 160, 40),
}

def draw_bbox(frame, x1, y1, x2, y2, label: str, color):
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    ty = max(y1 - 8, th + 4)
    cv2.rectangle(frame, (x1, ty - th - 4), (x1 + tw + 4, ty + 2), color, -1)
    cv2.putText(frame, label, (x1 + 2, ty - 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

def draw_hud(frame, mode_label: str, phase: int, fps: float, count: int):
    info = f"{mode_label} | Phase {phase} | FPS:{fps:.1f} | People:{count}"
    cv2.putText(frame, info, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)


# ==========================================
# LOAD COMPONENTS
# ==========================================
mode_label = "BG" if args.bg else "VISUAL"
print(f"\n{'='*55}")
print(f"  🚀 Pipeline Test | Phase {PHASE} | Tracker: {TRACKER_NAME.upper()} | Mode: {mode_label.upper()}")
print(f"{'='*55}\n")

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"📦 Device: {device.upper()}")

from ultralytics import YOLO
yolo = YOLO(MODEL_DETECT)
yolo.to(device)
print(f"✅ [Phase 1] YOLO loaded: {MODEL_DETECT}")

tracker   = None
classifier = None
embedder   = None
db         = None

if PHASE >= 2:
    from src.ai.tracker import create_tracker
    tracker = create_tracker(TRACKER_NAME, max_age=30, n_init=3)
    print(f"✅ [Phase 2] Tracker ready: {TRACKER_NAME.upper()}")
    
    from src.ai.feature_extractor import ClothingEmbedder
    embedder = ClothingEmbedder(model_path=MODEL_CLOTH, device=device)
    print(f"✅ [Phase 2] ClothingEmbedder ready")

if PHASE >= 3:
    from src.ai.classifier import ClothingClassifier
    classifier = ClothingClassifier(model_path=MODEL_CLOTH)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"✅ [Phase 3] ClothingClassifier ready")

    # DB — ลอง connect แต่ไม่ crash ถ้าไม่มี
    try:
        from src.services.database import DatabaseService
        db = DatabaseService()
        print(f"✅ [Phase 3] Database connected")
    except Exception as e:
        print(f"⚠️ [Phase 3] DB unavailable → บันทึกแค่รูปภาพ: {e}")
        db = None


# ==========================================
# OPEN VIDEO SOURCE  (รองรับ YouTube URL)
# ==========================================
import re
_YT_PATTERN = re.compile(r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/')

_resolved_source = SOURCE
if isinstance(SOURCE, str) and _YT_PATTERN.search(SOURCE):
    print(f"🔗 YouTube URL detected — resolving stream via yt-dlp...")
    try:
        import yt_dlp
        _ydl_opts = {
            "format": "best[ext=mp4]/best",
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(_ydl_opts) as ydl:
            _info = ydl.extract_info(SOURCE, download=False)
            _resolved_source = _info.get("url", SOURCE)
        print(f"✅ Stream resolved successfully")
        # Set FFmpeg options for streaming
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            "http_persistent;0|reconnect;1|reconnect_at_eof;1"
            "|reconnect_streamed;1|reconnect_delay_max;5|timeout;10000000"
        )
    except Exception as e:
        print(f"❌ yt-dlp failed: {e}")
        sys.exit(1)

cap = cv2.VideoCapture(_resolved_source)
if not cap.isOpened():
    print(f"❌ ไม่สามารถเปิด source: {SOURCE}")
    sys.exit(1)

print(f"\n▶️  เริ่ม (source={SOURCE})  |  {'กด Q เพื่อออก' if SHOW_WINDOW else 'กด Ctrl+C เพื่อหยุด'}\n")

# State Phase 3
analyzed_ids: dict = {}  # track_id → class_name
db_batch    : list = []
BATCH_SIZE  = 5

prev_time  = time.time()
frame_num  = 0
last_draw_data = []  # เก็บข้อมูลวาดกล่องของเฟรมล่าสุด (สำหรับเฟรมที่โดน skip)


# ==========================================
# def flush_db_batch — บันทึก batch ลง DB
# ==========================================
def flush_db_batch():
    global db_batch
    if db and db_batch:
        db.insert_detections_batch(db_batch)
        db_batch = []


# ==========================================
# MAIN LOOP
# ==========================================
try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("⚠️ วิดีโอจบ หรืออ่านเฟรมไม่ได้")
            break

        now = time.time()
        fps = 1.0 / (now - prev_time + 1e-9)
        prev_time = now
        frame_num += 1

        people_count = 0
        display = frame.copy() if SHOW_WINDOW else None

        # ── ข้าม frame ที่ไม่ใช่รอบ process (แสดงผลแต่ไม่ detect)
        if frame_num % FRAME_SKIP != 0:
            if SHOW_WINDOW and display is not None:
                # วาดกล่องของเฟรมก่อนหน้าค้างไว้ (ลดการกะพริบ)
                for draw_fn, args_tuple in last_draw_data:
                    draw_fn(display, *args_tuple)
                draw_hud(display, mode_label, PHASE, fps, people_count)
                cv2.imshow(f"Pipeline | Phase {PHASE}", display)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    print("⏹️  ผู้ใช้กด Q หยุดการทำงาน")
                    break
            continue

        # เคลียร์ข้อมูลวาดกล่องสำหรับเฟรมใหม่
        last_draw_data.clear()

        # ──────────────────────────────────────────────
        # PHASE 1 — Detection Only
        # ──────────────────────────────────────────────
        if PHASE == 1:
            results = yolo(frame, classes=[0], conf=CONF_THRESH, verbose=False, device=device)
            for box in (results[0].boxes or []):
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                w, h = x2-x1, y2-y1
                conf_val = float(box.conf[0])

                # Debug: แสดงขนาด box (สีแดง)
                if DEBUG and SHOW_WINDOW:
                    cv2.rectangle(display, (x1,y1), (x2,y2), (0,0,200), 1)
                    cv2.putText(display, f"{conf_val:.2f} {w}x{h}",
                                (x1, max(y1-4,10)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,0,255), 1)

                people_count += 1
                if SHOW_WINDOW:
                    args_tuple = (x1, y1, x2, y2, f"Person {conf_val:.2f}", COLORS["bbox"])
                    draw_bbox(display, *args_tuple)
                    last_draw_data.append((draw_bbox, args_tuple))

        # ──────────────────────────────────────────────
        # PHASE 2 & 3 — Tracking with Custom Feature Extractor
        # ──────────────────────────────────────────────
        elif PHASE in [2, 3]:
            # 1. Detection
            results = yolo(frame, classes=[0], conf=CONF_THRESH, verbose=False, device=device)
            boxes_list = []
            embeds_list = []
            cloth_labels_list = []
            
            if results and results[0].boxes:
                for box in results[0].boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    c = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    
                    emb = None
                    cloth_label = "Unknown"
                    if embedder is not None:
                         crop = frame[max(y1,0):y2, max(x1,0):x2]
                         if crop.size > 0:
                             res_tup = embedder.get_embedding(crop)
                             if isinstance(res_tup, tuple):
                                 emb, labels = res_tup
                                 if labels and labels != ["Unknown"]:
                                     cloth_label = " + ".join(labels)
                             else:
                                 emb = res_tup
                             
                    boxes_list.append([x1, y1, x2, y2, c, cls_id])
                    embeds_list.append(emb)
                    cloth_labels_list.append(cloth_label)

            # 2. Tracking with Custom Embeddings
            tracks = tracker.update(frame, yolo, device, CONF_THRESH, [0], embeds=embeds_list, boxes_list=boxes_list)
            
            for t in tracks:
                x1, y1, x2, y2 = t["bbox"]
                tid = t["track_id"]
                people_count += 1
                
                # แมตช์ข้ามกล่อง Tracking ให้เชื่อมกับกล่อง Detection (ด้วย Center Distance) เพื่อดึงชื่อเสื้อผ้า
                best_label = "Unknown"
                if cloth_labels_list:
                    tx, ty = (x1+x2)/2, (y1+y2)/2
                    best_dist = 999999
                    for i, b in enumerate(boxes_list):
                        bx, by = (b[0]+b[2])/2, (b[1]+b[3])/2
                        dist = (tx-bx)**2 + (ty-by)**2
                        if dist < best_dist and dist < 10000:
                            best_dist = dist
                            best_label = cloth_labels_list[i]
                            
                cls_label = best_label
                
                if PHASE == 2:
                    if SHOW_WINDOW:
                        color = COLORS["track"] if cls_label == "Unknown" else COLORS["cloth"]
                        args_tuple = (x1, y1, x2, y2, f"ID:{tid} [{cls_label}]", color)
                        draw_bbox(display, *args_tuple)
                        last_draw_data.append((draw_bbox, args_tuple))
                        
                elif PHASE == 3:
                    # ── สำหรับ Phase 3 บันทึกรูปและฐานข้อมูล
                    if tid in analyzed_ids:
                        if cls_label == "Unknown":
                            cls_label = analyzed_ids[tid]
                        else:
                            analyzed_ids[tid] = cls_label
                    else:
                        analyzed_ids[tid] = cls_label

                    # ใช้ Classifier เก่าช่วยทายถ้า best.pt หาไม่เจอ
                    if cls_label == "Unknown" and classifier is not None:
                        crop = frame[max(y1,0):y2, max(x1,0):x2]
                        if crop.size > 0:
                            cls_label, conf_cls, _ = classifier.predict(crop)
                            analyzed_ids[tid] = cls_label

                    # ── บันทึกรูปภาพ
                    out_folder = os.path.join(OUTPUT_DIR, cls_label)
                    os.makedirs(out_folder, exist_ok=True)
                    ts = int(time.time() * 1000)
                    img_path = os.path.join(out_folder, f"id{tid}_{ts}.jpg")
                    crop_save = frame[max(y1,0):y2, max(x1,0):x2]
                    if crop_save.size > 0:
                        cv2.imwrite(img_path, crop_save)

                    # ── Queue ลง DB
                    db_batch.append({
                        "camera_id":   CAMERA_ID,
                        "track_id":    tid,
                        "class_name":  cls_label,
                        "category":    "TOP",     
                        "color_profile": {},
                        "image_path":  img_path,
                    })
                    if len(db_batch) >= BATCH_SIZE:
                        flush_db_batch()

                    print(f"📸 ID:{tid} → {cls_label} (Tracked)")

                    if SHOW_WINDOW:
                        color = COLORS["cloth"] if cls_label != "Unknown" else COLORS["track"]
                        args_tuple = (x1, y1, x2, y2, f"ID:{tid} | {cls_label}", color)
                        draw_bbox(display, *args_tuple)
                        last_draw_data.append((draw_bbox, args_tuple))

        # ── Background mode: print stats ทุก 30 เฟรม
        if args.bg and (int(time.time() * 10) % 30 == 0):
            print(f"⏳ Running... FPS:{fps:.1f} | People:{people_count} | IDs seen:{len(analyzed_ids)}")

        # ── Visual mode: แสดงหน้าต่าง
        if SHOW_WINDOW and display is not None:
            draw_hud(display, mode_label, PHASE, fps, people_count)
            cv2.imshow(f"Pipeline | Phase {PHASE}", display)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                print("⏹️  ผู้ใช้กด Q หยุดการทำงาน")
                break

except KeyboardInterrupt:
    print("\n⏹️  Ctrl+C — หยุดการทำงาน")


# ==========================================
# CLEANUP
# ==========================================
flush_db_batch()  # flush ที่เหลือ
cap.release()
if SHOW_WINDOW:
    cv2.destroyAllWindows()
if db:
    db.close()

if PHASE == 3:
    print(f"\n📊 สรุป:")
    print(f"   Unique IDs ที่เจอ: {len(analyzed_ids)}")
    for tid, cls in analyzed_ids.items():
        print(f"   ID {tid:>4} → {cls}")
    print(f"   รูปบันทึกที่: {os.path.abspath(OUTPUT_DIR)}/")
    print(f"\n   ดูผลใน DB ด้วย: python pipeline_test.py --results")

print("\n✅ เสร็จสิ้น!")
