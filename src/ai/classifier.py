import os
import torch  
from ultralytics import YOLO

class ClothingClassifier:
    def __init__(self, model_path='models/clothing_classifier.pt'):
        self.model = None
        
        # 2. เช็ค Device
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"👕 Clothing Classifier using device: {self.device.upper()}")

        if not os.path.exists(model_path):
            print(f"⚠️ Warning: Model file not found at '{model_path}'")
            return

        try:
            self.model = YOLO(model_path)
            self.model.to(self.device) # <--- 3. ย้ายไป GPU
            print(f"✅ Clothing Classifier Loaded! ({model_path})")
        except Exception as e:
            print(f"❌ Error loading model: {e}")
            self.model = None

    def predict(self, image_crop):
        if self.model is None or image_crop is None or image_crop.size == 0:
            return "Unknown", 0.0, None

        try:
            # 4. ส่ง device เข้าไปตอน predict
            results = self.model(image_crop, verbose=False, device=self.device)
            
            # ... (โค้ดส่วนอ่านผลลัพธ์เหมือนเดิม) ...
            if not results: return "Unknown", 0.0, None
            result = results[0]
            
            if hasattr(result, 'probs') and result.probs is not None:
                top1_index = result.probs.top1
                class_name = result.names[top1_index]
                conf = result.probs.top1conf.item()
                return class_name, conf, None
            
            elif hasattr(result, 'boxes') and result.boxes is not None and len(result.boxes) > 0:
                best_box = sorted(result.boxes, key=lambda x: x.conf.item(), reverse=True)[0]
                class_id = int(best_box.cls.item())
                class_name = result.names[class_id]
                conf = best_box.conf.item()
                bbox = tuple(map(int, best_box.xyxy[0].tolist()))  # (x1, y1, x2, y2)
                return class_name, conf, bbox

            return "Unknown", 0.0, None

        except Exception as e:
            print(f"⚠️ Prediction Error: {e}")
            return "Unknown", 0.0, None