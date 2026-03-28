"""
tracker.py — Unified Tracker Wrappers
รองรับ 3 algorithm: DeepSORT | ByteTrack | BoT-SORT

Interface มาตรฐาน (ทุก class):
    tracker.update(frame, yolo_model, device, conf, classes)
    → list of {"track_id": int, "bbox": (x1,y1,x2,y2), "conf": float}
"""


# ============================================================
# DeepSORT (ใช้ Re-ID appearance feature — เสถียรที่สุดเมื่อคนซ้อนทับ)
# ต้องติดตั้ง: pip install deep-sort-realtime
# ============================================================
class DeepSortTracker:
    def __init__(self, max_age: int = 90, n_init: int = 3, max_iou_distance: float = 0.9):
        from deep_sort_realtime.deepsort_tracker import DeepSort
        self.tracker = DeepSort(
            max_age=max_age,
            n_init=n_init,
            max_iou_distance=max_iou_distance,
            embedder="mobilenet",
            half=True,
            embedder_gpu=True,
        )

    def update(self, frame, yolo_model, device: str, conf: float, classes: list) -> list:
        results = yolo_model(frame, classes=classes, conf=conf, verbose=False, device=device)
        detections = self._parse(results[0])
        if not detections:
            self.tracker.update_tracks([], frame=frame)
            return []
        raw = self.tracker.update_tracks(detections, frame=frame)
        return [
            {
                "track_id": t.track_id,
                "bbox": tuple(map(int, t.to_ltrb())),
                "conf": t.det_conf or 0.0,
            }
            for t in raw if t.is_confirmed()
        ]

    @staticmethod
    def _parse(r):
        if r is None or r.boxes is None:
            return []
        out = []
        for box in r.boxes:
            x1, y1, x2, y2 = map(float, box.xyxy[0])
            out.append(([x1, y1, x2 - x1, y2 - y1], float(box.conf[0]), "person"))
        return out


# ============================================================
# ByteTrack (built-in YOLO — เร็ว เบา เหมาะ real-time)
# ไม่ต้องติดตั้งอะไรเพิ่ม
# ============================================================
class ByteTrackTracker:
    def update(self, frame, yolo_model, device: str, conf: float, classes: list) -> list:
        results = yolo_model.track(
            frame,
            classes=classes,
            conf=conf,
            tracker="bytetrack.yaml",
            persist=True,
            verbose=False,
            device=device,
        )
        return self._parse(results[0])

    @staticmethod
    def _parse(r):
        if r is None or r.boxes is None or r.boxes.id is None:
            return []
        out = []
        for box in r.boxes:
            if box.id is None:
                continue
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            out.append({
                "track_id": int(box.id[0]),
                "bbox": (x1, y1, x2, y2),
                "conf": float(box.conf[0]),
            })
        return out


# ============================================================
# BoT-SORT (built-in YOLO — แม่นกว่า ByteTrack, ใช้ camera motion compensation)
# ไม่ต้องติดตั้งอะไรเพิ่ม
# ============================================================
class BotSortTracker:
    def update(self, frame, yolo_model, device: str, conf: float, classes: list) -> list:
        results = yolo_model.track(
            frame,
            classes=classes,
            conf=conf,
            tracker="botsort.yaml",
            persist=True,
            verbose=False,
            device=device,
        )
        return self._parse(results[0])

    @staticmethod
    def _parse(r):
        if r is None or r.boxes is None or r.boxes.id is None:
            return []
        out = []
        for box in r.boxes:
            if box.id is None:
                continue
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            out.append({
                "track_id": int(box.id[0]),
                "bbox": (x1, y1, x2, y2),
                "conf": float(box.conf[0]),
            })
        return out


# ============================================================
# BoxMOT (BoT-SORT standalone — รองรับ Custom Embeddings นอกโมเดล)
# ต้องติดตั้ง: pip install boxmot
# ============================================================
class BoxMotTracker:
    def __init__(self, track_buffer: int = 90, match_thresh: float = 0.9, proximity_thresh: float = 0.6):
        from boxmot import BoTSORT
        from pathlib import Path
        # กำหนด model_weights=Path('') เพื่อไม่โหลดโมเดล Re-ID ในตัว
        self.tracker = BoTSORT(
            model_weights=Path(''), 
            device='cuda' if __import__('torch').cuda.is_available() else 'cpu',
            fp16=False,
            track_buffer=track_buffer,          # จำ ID ไว้แม้ว่าจะมองไม่เห็น 90 เฟรม
            match_thresh=match_thresh,          # น้ำหนักรวมในการ Match สูงขึ้น 
            proximity_thresh=proximity_thresh   # ให้น้ำหนัก Motion / IoU มากขึ้น เพื่อไม่ให้ขึ้นกับ ReID เพียงอย่างเดียว
        )

    def update(self, frame, yolo_model, device: str, conf: float, classes: list, embeds: list = None, boxes_list: list = None) -> list:
        import numpy as np
        
        # ถ้าไม่มีการผ่าน boxes เข้ามา ให้ detect เอง
        if boxes_list is None:
            results = yolo_model(frame, classes=classes, conf=conf, verbose=False, device=device)
            if not results or results[0].boxes is None:
                return []
            
            dets = []
            for box in results[0].boxes:
                x1, y1, x2, y2 = map(float, box.xyxy[0])
                c = float(box.conf[0])
                cls_id = int(box.cls[0])
                dets.append([x1, y1, x2, y2, c, cls_id])
            dets = np.array(dets)
        else:
            # แปลงรับ external bbs
            if not boxes_list:
                return []
            dets = np.array(boxes_list)
            
        if len(dets) == 0:
            return []
            
        embs_arr = None
        if embeds and len(embeds) == len(dets):
            embs_arr = np.array(embeds)
            
        # BoxMot signature: update(dets: ndarray, img: ndarray, embs: ndarray = None)
        # return: ndarray [x1, y1, x2, y2, track_id, conf, cls, ind]
        try:
           tracks = self.tracker.update(dets, frame, embs=embs_arr)
        except TypeError:
           # Fallback in case old version or different signature
           tracks = self.tracker.update(dets, frame)

        out = []
        for t in tracks:
            out.append({
                "track_id": int(t[4]),
                "bbox": (int(t[0]), int(t[1]), int(t[2]), int(t[3])),
                "conf": float(t[5]) if len(t) > 5 else 1.0,
            })
        return out


# ============================================================
# Factory — สร้าง tracker จากชื่อ string
# ============================================================
TRACKERS = {
    "deepsort":  DeepSortTracker,
    "bytetrack": ByteTrackTracker,
    "botsort":   BotSortTracker,
    "boxmot":    BoxMotTracker,
}

def create_tracker(name: str = "deepsort", **kwargs):
    """
    สร้าง tracker จากชื่อ
    Args:
        name: "deepsort" | "bytetrack" | "botsort" | "boxmot"
        **kwargs: ส่งต่อเฉพาะ DeepSortTracker (max_age, n_init, max_iou_distance)
    """
    name = name.lower()
    if name not in TRACKERS:
        raise ValueError(f"Unknown tracker '{name}'. Choose from: {list(TRACKERS.keys())}")
    cls = TRACKERS[name]
    if name == "deepsort":
        return cls(**kwargs)
    return cls()
