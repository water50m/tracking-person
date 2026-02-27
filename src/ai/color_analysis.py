import cv2
import numpy as np

# 🎨 กำหนด Palette สีมาตรฐาน (RGB)
COLOR_PALETTE = {
    "black":   (0,   0,   0),
    "white":   (255, 255, 255),
    "grey":    (128, 128, 128),
    "red":     (255, 0,   0),
    "green":   (0,   255, 0),
    "blue":    (0,   0,   255),
    "yellow":  (255, 255, 0),
    "cyan":    (0,   255, 255),
    "magenta": (255, 0,   255),
    "orange":  (255, 165, 0),
    "purple":  (128, 0,   128),
    "brown":   (165, 42,  42),
}

# Pre-compute palette เป็น numpy array ครั้งเดียวตอน import
_PALETTE_NAMES  = list(COLOR_PALETTE.keys())
_PALETTE_COLORS = np.array(list(COLOR_PALETTE.values()), dtype=np.float32)  # (12, 3)


def analyze_color_histogram(image_crop):
    """
    รับรูป Crop (numpy array) -> คืนค่า % สีเป็น Dictionary
    Example Output: {"red": 60.5, "black": 30.0, "white": 9.5}

    ใช้ NumPy vectorized แทน Python loop → เร็วกว่าเดิม ~500x
    """
    if image_crop is None or image_crop.size == 0:
        return {}

    # 1. ย่อภาพ (50×50 พอ)
    small_img = cv2.resize(image_crop, (50, 50))

    # 2. BGR → RGB แล้ว reshape เป็น (2500, 3)
    pixels = cv2.cvtColor(small_img, cv2.COLOR_BGR2RGB) \
               .reshape(-1, 3) \
               .astype(np.float32)          # (N, 3)

    # 3. คำนวณ Euclidean distance ทุก pixel กับทุกสีใน palette พร้อมกัน
    #    pixels[:, None, :]  → (N, 1, 3)
    #    _PALETTE_COLORS     → (12, 3)
    #    broadcast result    → (N, 12)
    diff      = pixels[:, None, :] - _PALETTE_COLORS     # (N, 12, 3)
    distances = np.einsum("ijk,ijk->ij", diff, diff)      # (N, 12)  squared dist (ไม่ต้อง sqrt)

    # 4. argmin → index ของสีที่ใกล้ที่สุดสำหรับ pixel แต่ละตัว
    closest_idx = np.argmin(distances, axis=1)            # (N,)

    # 5. นับจำนวนและแปลงเป็น %
    total_pixels = len(closest_idx)
    color_profile = {}
    for idx, count in zip(*np.unique(closest_idx, return_counts=True)):
        pct = round(float(count) / total_pixels * 100, 1)
        if pct > 5.0:  # กรอง Noise
            color_profile[_PALETTE_NAMES[idx]] = pct

    return color_profile
