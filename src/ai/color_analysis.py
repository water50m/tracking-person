import cv2
import numpy as np
import warnings

# ปิด warning ของ rembg ถ้ามี
warnings.filterwarnings("ignore")

try:
    from rembg import remove
    REMBG_AVAILABLE = True
except ImportError:
    REMBG_AVAILABLE = False

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

_PALETTE_NAMES  = list(COLOR_PALETTE.keys())
# Pre-compute palette BGR -> HSV
_PALETTE_COLORS_BGR = np.array([COLOR_PALETTE[k][::-1] for k in _PALETTE_NAMES], dtype=np.uint8).reshape(1, 12, 3)
_PALETTE_COLORS_HSV = cv2.cvtColor(_PALETTE_COLORS_BGR, cv2.COLOR_BGR2HSV).reshape(12, 3).astype(np.float32)

def remove_background_grabcut(img):
    """Fallback: ใช้ GrabCut ตัด Background ออกเพื่อเหลือแต่ Foreground"""
    h, w = img.shape[:2]
    # ให้ทั้งหมดมีความน่าจะเป็นที่จะเป็น Foreground (PR_FGD) ก่อน
    mask = np.ones((h, w), np.uint8) * cv2.GC_PR_FGD
    
    # กำหนดให้ขอบภาพ 5% มีความน่าจะเป็นที่จะเป็น Background (PR_BGD)
    margin_w, margin_h = max(1, int(w * 0.05)), max(1, int(h * 0.05))
    cv2.rectangle(mask, (0, 0), (w-1, h-1), cv2.GC_PR_BGD, margin_w)
    
    # มุมซ้ายบน ซ้ายขวาบน เป็น Background (BGD) แน่นอน 100% (ส่วนใหญ่เป็นพื้นหลังหรือกล้อง)
    mask[0:margin_h, 0:margin_w] = cv2.GC_BGD
    mask[0:margin_h, w-margin_w:w] = cv2.GC_BGD
    
    bgdModel = np.zeros((1, 65), np.float64)
    fgdModel = np.zeros((1, 65), np.float64)
    
    try:
        cv2.grabCut(img, mask, None, bgdModel, fgdModel, 3, cv2.GC_INIT_WITH_MASK)
        return np.where((mask == 2) | (mask == 0), 0, 1).astype(np.uint8)
    except:
        return np.ones(img.shape[:2], dtype=np.uint8)

def analyze_color_histogram(image_crop, return_map=False):
    """
    รับรูปภาพ (numpy array) ที่เป็น Bounding Box ของเสื้อผ้าจากโมเดล
    1. ตัด Background ออกหน้าเหลือแต่ตัวเสื้อจริงๆ (ใช้ rembg หรือ GrabCut)
    2. คำนวณความใกล้เคียงสีใน HSV Space ที่ทนต่อแสงเงา 
    คืนค่าเป็น Dictionary เช่น {"red": 60.5, "black": 30.0}
    """
    if image_crop is None or image_crop.size == 0:
        return ({}, None) if return_map else {}

    h, w = image_crop.shape[:2]
    if h < 20 or w < 20: 
        return ({}, None) if return_map else {}

    # ยกเลิก Torso Cropping ไปเลย เพราะเรา assume ว่า crop ที่ส่งมา
    # คืองานเสื้อผ้าที่ถูกครอบมาแบบพอดีแล้ว (จากโมเดลเสื้อผ้าโดยตรง)

    # ย่อภาพลงนิดหน่อยเพื่อให้การทำ bg removal หรือคำนวณสีทำได้เร็วมาก (Real-time)
    small_img = cv2.resize(image_crop, (64, 64))

    # 2. Cut BG (ลบพื้นหลัง)
    if REMBG_AVAILABLE:
        try:
            bg_removed = remove(small_img) # คืนค่าเป็น RGBA/BGRA array
            alpha = bg_removed[:, :, 3]
            fg_mask = (alpha > 50).astype(np.uint8)
        except:
            fg_mask = remove_background_grabcut(small_img)
    else:
        fg_mask = remove_background_grabcut(small_img)

    # ดึงเฉพาะ pixel ที่เป็น Foreground
    bgr_fg = small_img[fg_mask == 1]
    
    # ถ้าโดนตัดหายเกลี้ยงเพราะสีกลืนกันมาก ให้ใช้ภาพทั้งกรอบแทน (Fallback)
    if len(bgr_fg) < 50: 
        bgr_fg = small_img.reshape(-1, 3)
        fg_mask = np.ones((64, 64), dtype=np.uint8)

    # 3. แปลง BGR เป็น HSV
    bgr_fg_img = bgr_fg.reshape(-1, 1, 3).astype(np.uint8)
    hsv_pixels = cv2.cvtColor(bgr_fg_img, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.float32)

    # 4. คำนวณระยะทางใน HSV 
    # H (0-179), S (0-255), V (0-255)
    H_pixels, S_pixels, V_pixels = hsv_pixels[:, 0:1], hsv_pixels[:, 1:2], hsv_pixels[:, 2:3]
    H_pal, S_pal, V_pal = _PALETTE_COLORS_HSV[:, 0], _PALETTE_COLORS_HSV[:, 1], _PALETTE_COLORS_HSV[:, 2]

    # การหาความต่างของ Hue (ต้องวนรอบวงกลม 180)
    diff_H = np.abs(H_pixels - H_pal)
    diff_H = np.minimum(diff_H, 180 - diff_H) # (N, 12)
    
    diff_S = np.abs(S_pixels - S_pal) # (N, 12)
    diff_V = np.abs(V_pixels - V_pal) # (N, 12)

    # 5. ใส่ Weight ป้องกันแสงเงา
    # การให้ H มีน้ำหนักมากทำให้แบ่งสีได้ดี แต่ถ้าสีมืดลงมากๆ (V ต่ำ) หรือ กลายเป็นเทา/ขาว (S ต่ำ) H จะไม่มีความหมาย
    # จึงต้องถ่วงน้ำหนัก H ด้วย S และ V จริงของ pixel ตัวมันเอง
    S_weight = S_pixels / 255.0  # ค่า 0-1
    V_weight = V_pixels / 255.0  # ค่า 0-1
    
    # ถ้าค่าเป็นสีมืด (ดำ) หรือค่าไม่สด (ส่วนที่สะท้อนแสงมากจนเป็นขาว) H แก่นี้จะลดน้ำหนักตัวเองลง
    W_H = 2.0 * S_weight * V_weight 
    W_S = 1.0 # ความสด (เทาไหม)
    W_V = 0.5 # ให้ค่าน้ำหนักความสว่างน้อยสุด ช่วยให้สีในที่แสงน้อยและสว่างถูกตรวจจับได้เหมือนกัน

    # Euclidean distance ถ่วงน้ำหนักใน 3 มิติ HSV
    distances = (W_H * diff_H)**2 + (W_S * diff_S)**2 + (W_V * diff_V)**2 # shape: (N, 12)

    # 6. เลือกค่าสีที่ใกล้ที่สุดให้แต่ละ Pixel
    closest_idx = np.argmin(distances, axis=1) # (N,)

    # 7. นับจำนวนและแปลงเป็น Percentage
    total_pixels = len(closest_idx)
    color_profile = {}
    for idx, count in zip(*np.unique(closest_idx, return_counts=True)):
        pct = round(float(count) / total_pixels * 100, 1)
        if pct > 5.0:  # กรอง Noise สิ่งที่เล็กเกิน 5% ทิ้งไป
            color_profile[_PALETTE_NAMES[idx]] = pct

    if return_map:
        # Create a 4-channel BGRA image for the map
        map_img_rgba = np.zeros((64, 64, 4), dtype=np.uint8)
        assigned_colors_bgr = _PALETTE_COLORS_BGR[0, closest_idx] # Shape: (N, 3)
        
        # Fill in the foreground pixels with the assigned colors
        map_img_rgba[fg_mask == 1, :3] = assigned_colors_bgr
        map_img_rgba[fg_mask == 1, 3] = 255 # Full opacity for foreground
        
        return color_profile, map_img_rgba

    return color_profile

# =========================================================================
# ระบบวิเคราะห์สีแบบ HSL Soft Binning (มีกลุ่มสีทับซ้อน Overlapping)
# =========================================================================

COLOR_GROUPS_MAPPING = {
    "light": ["white", "gray", "yellow", "cyan", "pink", "light_blue"],
    "dark": ["black", "gray", "navy", "dark_green", "brown", "dark_red"],
    "warm": ["red", "orange", "yellow", "brown", "pink"],
    "cool": ["blue", "navy", "cyan", "green", "purple", "light_blue"],
    "achromatic": ["white", "black", "gray"]
}

def analyze_color_groups_hsl(image_crop, return_map=False):
    """
    วิเคราะห์สีด้วย HSL โดยใช้กฎ Overlapping
    คืนค่าเป็น Dictionary ประกอบด้วย dominant_colors, color_distribution, matched_groups, primary_color
    """
    if image_crop is None or image_crop.size == 0:
        empty_res = {"dominant_colors": [], "color_distribution": {}, "matched_groups": [], "primary_color": "unknown"}
        return (empty_res, None) if return_map else empty_res

    h, w = image_crop.shape[:2]
    if h < 20 or w < 20: 
        empty_res = {"dominant_colors": [], "color_distribution": {}, "matched_groups": [], "primary_color": "unknown"}
        return (empty_res, None) if return_map else empty_res

    small_img = cv2.resize(image_crop, (64, 64))

    if REMBG_AVAILABLE:
        try:
            bg_removed = remove(small_img)
            alpha = bg_removed[:, :, 3]
            fg_mask = (alpha > 50).astype(np.uint8)
        except:
            fg_mask = remove_background_grabcut(small_img)
    else:
        fg_mask = remove_background_grabcut(small_img)

    bgr_fg = small_img[fg_mask == 1]
    
    if len(bgr_fg) < 50: 
        bgr_fg = small_img.reshape(-1, 3)
        fg_mask = np.ones((64, 64), dtype=np.uint8)

    # 1. แปลง BGR เป็น HLS (Hue, Lightness, Saturation)
    bgr_fg_img = bgr_fg.reshape(-1, 1, 3).astype(np.uint8)
    hls_pixels = cv2.cvtColor(bgr_fg_img, cv2.COLOR_BGR2HLS).reshape(-1, 3).astype(np.float32)

    # OpenCV HLS: H (0-179), L (0-255), S (0-255)
    H, L, S = hls_pixels[:, 0], hls_pixels[:, 1], hls_pixels[:, 2]
    total_pixels = len(H)

    # 2. สร้าง Overlapping Masks แบบรวดเร็วด้วย Numpy
    m_black = (L < 40) | ((S < 40) & (L < 60))
    m_white = (L > 200) | ((S < 30) & (L > 180))
    m_gray = (S < 50) & (L >= 30) & (L <= 210)

    m_chromatic = (L >= 20) & (L <= 220) & (S >= 35)

    m_red       = m_chromatic & ((H < 12) | (H > 165)) & (L >= 80) & (L <= 180)
    m_dark_red  = m_chromatic & ((H < 15) | (H > 165)) & (L < 90)
    m_pink      = m_chromatic & ((H < 15) | (H > 160)) & (L > 150)
    
    m_orange    = m_chromatic & (H >= 8) & (H <= 25) & (L >= 90)
    m_brown     = m_chromatic & (H >= 5) & (H <= 25) & (L < 120)
    
    m_yellow    = m_chromatic & (H >= 20) & (H <= 35)
    
    m_green     = m_chromatic & (H >= 30) & (H <= 85) & (L >= 70)
    m_dark_green= m_chromatic & (H >= 30) & (H <= 85) & (L < 90)
    
    m_cyan      = m_chromatic & (H >= 80) & (H <= 100)
    
    m_blue      = m_chromatic & (H >= 95) & (H <= 135) & (L >= 70)
    m_navy      = m_chromatic & (H >= 95) & (H <= 135) & (L < 90)
    m_light_blue= m_chromatic & (H >= 95) & (H <= 135) & (L > 160)
    
    m_purple    = m_chromatic & (H >= 125) & (H <= 165)

    # นับคะแนน (1 pixel โหวตได้หลายสี เพราะ overlap)
    counts = {
        "black": np.sum(m_black), "white": np.sum(m_white), "gray": np.sum(m_gray),
        "red": np.sum(m_red), "dark_red": np.sum(m_dark_red), "pink": np.sum(m_pink),
        "orange": np.sum(m_orange), "brown": np.sum(m_brown), "yellow": np.sum(m_yellow),
        "green": np.sum(m_green), "dark_green": np.sum(m_dark_green), "cyan": np.sum(m_cyan),
        "blue": np.sum(m_blue), "navy": np.sum(m_navy), "light_blue": np.sum(m_light_blue),
        "purple": np.sum(m_purple)
    }

    # 3. สรุป Color Distribution
    color_distribution = {}
    for color, count in counts.items():
        pct = round((float(count) / total_pixels) * 100, 1)
        if pct > 5.0:  # ตัดสียิบย่อยน้อยกว่า 5% ทิ้ง
            color_distribution[color] = pct

    detected_base_colors = list(color_distribution.keys())
    
    # 4. Map สีเข้า Group ใหญ่
    matched_groups = set()
    for base_color in detected_base_colors:
        for group, members in COLOR_GROUPS_MAPPING.items():
            if base_color in members:
                matched_groups.add(group)

    primary_color = "unknown"
    if color_distribution:
        primary_color = max(color_distribution, key=color_distribution.get)

    result_dict = {
        "dominant_colors": detected_base_colors,
        "color_distribution": color_distribution,
        "matched_groups": list(matched_groups),
        "primary_color": primary_color
    }

    if return_map:
        # วาด map (สำหรับทดสอบเท่านั้น ไม่ได้ระบายสีตรงจุดทับซ้อนสมบูรณ์นัก แต่สร้างให้หน้าต่างไม่แครช)
        map_img_rgba = np.zeros((64, 64, 4), dtype=np.uint8)
        map_img_rgba[fg_mask == 1, 3] = 255
        return result_dict, map_img_rgba

    return result_dict

