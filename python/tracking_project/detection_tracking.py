import cv2
import torch
from torch.version import cuda
from ultralytics import YOLO
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'ai'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'services'))
from color_system import (
    analyze_detailed_colors, get_color_groups, 
    get_primary_detailed_color, get_primary_color_group
)
from database import DatabaseService

def setup_device():
    """ตั้งค่า device สำหรับการประมวลผล"""
    print("CUDA Available:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("Device Name:", torch.cuda.get_device_name(0))
        return "cuda"
    else:
        print("คำเตือน: ไม่พบ CUDA ระบบจะรันบน CPU แทน ซึ่งจะทำให้วิดีโอประมวลผลช้ามาก")
        return "cpu"

def load_models(device):
    """โหลดโมเดล YOLO ทั้งหมด"""
    person_model = YOLO('yolo11n.pt')
    custom_model = YOLO(r'E:\ALL_CODE\my-project\models\prepare_dataset.pt')
    return person_model, custom_model

def init_video_capture(video_path):
    """เปิดไฟล์วิดีโอและคืนค่าข้อมูลเบื้องต้น"""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: ไม่สามารถเปิดไฟล์วิดีโอได้ {video_path}")
        exit()
    
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    return cap, frame_width, frame_height

def detect_persons(person_model, frame, device):
    """ตรวจจับคนและ tracking"""
    return person_model.track(
        frame, persist=True, classes=[0], device=device, 
        verbose=False, tracker="bytetrack.yaml", conf=0.3
    )

def detect_clothes(custom_model, person_crop, device, conf_threshold=0.40):
    """ตรวจจับเสื้อผ้าจากภาพครอปคน"""
    results = custom_model(person_crop, device=device, verbose=False)
    detected_clothes = []
    
    for c_res in results:
        for c_box in c_res.boxes:
            if float(c_box.conf[0]) > conf_threshold:
                cls_name = custom_model.names[int(c_box.cls[0])]
                if cls_name not in detected_clothes:
                    detected_clothes.append(cls_name)
    
    return detected_clothes

def analyze_person_features(person_crop, custom_model, device):
    """วิเคราะห์คุณสมบัติของคน (เสื้อผ้า + สีละเอียด + กลุ่มสี)"""
    clothes = detect_clothes(custom_model, person_crop, device)
    detailed_colors = analyze_detailed_colors(person_crop)
    color_groups = get_color_groups(detailed_colors)
    
    return {
        "clothes": clothes,
        "detailed_colors": detailed_colors,
        "color_groups": color_groups,
        "primary_detailed_color": get_primary_detailed_color(detailed_colors),
        "primary_color_group": get_primary_color_group(color_groups)
    }

def update_track_history(track_history, track_id, features, frame_count):
    """อัปเดตข้อมูลใน track_history"""
    if track_id not in track_history:
        track_history[track_id] = {
            "clothes": [],
            "detailed_colors": {},
            "color_groups": {},
            "primary_detailed_color": "unknown",
            "primary_color_group": "unknown",
            "last_seen": frame_count,
            "confidence": 0.0
        }
    
    # อัปเดตเฉพาะถ้ามีข้อมูลใหม่
    if features["clothes"] or features["detailed_colors"]:
        track_history[track_id].update(features)
        track_history[track_id]["last_seen"] = frame_count
        track_history[track_id]["confidence"] = min(1.0, track_history[track_id]["confidence"] + 0.1)

def cleanup_old_tracks(track_history, current_ids, frame_count, timeout=60):
    """ลบข้อมูล track ที่หมดอายุ"""
    keys_to_delete = []
    for track_id in track_history.keys():
        if (track_id not in current_ids and 
            frame_count - track_history[track_id]["last_seen"] > timeout):
            keys_to_delete.append(track_id)
    
    for k in keys_to_delete:
        del track_history[k]

def draw_person_box(frame, box, track_id, track_history):
    """วาดกรอบคนและข้อมูล"""
    x1, y1, x2, y2 = box
    
    # สร้างข้อความแสดงผล
    if track_id in track_history:
        data = track_history[track_id]
        clothes_text = ", ".join(data["clothes"]) if data["clothes"] else "Unknown"
        primary_color = data.get("primary_detailed_color", "unknown")
        status_text = f'ID: {track_id} | {clothes_text} | {primary_color}'
    else:
        status_text = f'ID: {track_id} | Unknown'
    
    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
    cv2.putText(frame, status_text, (x1, y1 + 10), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

def draw_clothes_boxes(frame, person_box, clothes_results, custom_model):
    """วาดกรอบเสื้อผ้า"""
    x1, y1 = person_box[:2]
    
    for c_res in clothes_results:
        for c_box in c_res.boxes:
            if float(c_box.conf[0]) > 0.40:
                cx1, cy1, cx2, cy2 = map(int, c_box.xyxy[0])
                orig_x1, orig_y1 = x1 + cx1, y1 + cy1
                orig_x2, orig_y2 = x1 + cx2, y1 + cy2
                cv2.rectangle(frame, (orig_x1, orig_y1), (orig_x2, orig_y2), (0, 255, 0), 1)

def process_single_person(person_model, custom_model, frame, box, track_id, 
                         track_history, frame_count, device, frame_width, frame_height, db=None):
    """ประมวลผลคนแต่ละคน"""
    x1, y1, x2, y2 = box
    
    # จำกัดกรอบไม่ให้เกินขอบภาพ
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(frame_width, x2), min(frame_height, y2)
    
    # ครอปภาพคน
    person_crop = frame[y1:y2, x1:x2]
    if person_crop.size > 0:
        # ตรวจจับเสื้อผ้าและวิเคราะห์สี
        features = analyze_person_features(person_crop, custom_model, device)
        
        # อัปเดตประวัติ
        update_track_history(track_history, track_id, features, frame_count)
        
        # บันทึกลงฐานข้อมูล (ถ้ามี database service)
        if db is not None:
            try:
                db.insert_detection(
                    camera_id="CAM-01",
                    track_id=int(track_id),
                    class_name="person",
                    image_path="",
                    category="person",
                    detailed_colors=features["detailed_colors"],
                    color_groups=features["color_groups"],
                    primary_detailed_color=features["primary_detailed_color"],
                    primary_color_group=features["primary_color_group"],
                    clothes=features["clothes"],
                    bbox=[int(x1), int(y1), int(x2), int(y2)]
                )
            except Exception as e:
                print(f"❌ Database save error for track {track_id}: {e}")
        
        # วาดผลลัพธ์
        draw_person_box(frame, (x1, y1, x2, y2), track_id, track_history)
        
        # วาดกรอบเสื้อผ้า (ต้องได้รับ clothes_results จาก detect_clothes)
        clothes_results = custom_model(person_crop, device=device, verbose=False)
        draw_clothes_boxes(frame, (x1, y1, x2, y2), clothes_results, custom_model)

def main():
    """ฟังก์ชันหลัก"""
    # Setup
    device = setup_device()
    person_model, custom_model = load_models(device)
    video_path = r'E:\ALL_CODE\my-project\temp_videos\CAM-01_4p-c0-new.mp4'
    cap, frame_width, frame_height = init_video_capture(video_path)
    
    # Database service
    try:
        db = DatabaseService()
        print("✅ Database service initialized")
    except Exception as e:
        print(f"⚠️  Database service failed to initialize: {e}")
        print("   ระบบจะทำงานโดยไม่บันทึกลงฐานข้อมูล")
        db = None
    
    # Memory system
    track_history = {}
    frame_count = 0
    
    print("กำลังประมวลผลวิดีโอ... กด 'q' เพื่อออก")
    
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break
        
        frame_count += 1
        current_ids = []
        
        # ตรวจจับคน
        person_results = detect_persons(person_model, frame, device)
        
        if person_results[0].boxes.id is not None:
            boxes = person_results[0].boxes.xyxy.cpu().numpy().astype(int)
            ids = person_results[0].boxes.id.cpu().numpy().astype(int)
            
            for box, track_id in zip(boxes, ids):
                current_ids.append(track_id)
                process_single_person(
                    person_model, custom_model, frame, box, track_id,
                    track_history, frame_count, device, frame_width, frame_height, db
                )
        
        # ลบข้อมูลเก่า
        cleanup_old_tracks(track_history, current_ids, frame_count)
        
        # แสดงผล
        cv2.imshow('Tracking with Attribute Memory', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()
    
    # ปิด database connection
    if db is not None:
        db.close()

if __name__ == "__main__":
    main()