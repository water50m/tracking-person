#!/usr/bin/env python3
"""
ระบบสีละเอียดและการจัดกลุ่มสี
Detailed Color System with Grouping for Tracking and Search
"""

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

# ============================================
# 🎨 ระบบสีละเอียด (Detailed Colors) - สำหรับ Tracking
# ============================================

# ช่วงสีละเอียดใน HSV Space (H: 0-179, S: 0-255, V: 0-255)
DETAILED_COLOR_RANGES = {
    # 🔴 Red shades
    "red": {
        "h_range": (0, 10),
        "s_range": (100, 255),
        "v_range": (50, 255)
    },
    "dark_red": {
        "h_range": (0, 10),
        "s_range": (50, 255),
        "v_range": (20, 80)
    },
    "crimson": {
        "h_range": (0, 8),
        "s_range": (150, 255),
        "v_range": (80, 180)
    },
    "scarlet": {
        "h_range": (0, 8),
        "s_range": (200, 255),
        "v_range": (150, 255)
    },
    "maroon": {
        "h_range": (0, 10),
        "s_range": (100, 200),
        "v_range": (30, 90)
    },
    
    # 🟠 Orange shades
    "orange": {
        "h_range": (10, 25),
        "s_range": (100, 255),
        "v_range": (80, 255)
    },
    "dark_orange": {
        "h_range": (10, 25),
        "s_range": (100, 255),
        "v_range": (50, 120)
    },
    "amber": {
        "h_range": (20, 35),
        "s_range": (150, 255),
        "v_range": (150, 255)
    },
    "peach": {
        "h_range": (8, 20),
        "s_range": (50, 150),
        "v_range": (180, 255)
    },
    "coral": {
        "h_range": (8, 15),
        "s_range": (150, 255),
        "v_range": (180, 255)
    },
    
    # 🟡 Yellow shades
    "yellow": {
        "h_range": (20, 40),
        "s_range": (100, 255),
        "v_range": (150, 255)
    },
    "gold": {
        "h_range": (25, 40),
        "s_range": (150, 255),
        "v_range": (150, 220)
    },
    "light_yellow": {
        "h_range": (20, 40),
        "s_range": (30, 100),
        "v_range": (200, 255)
    },
    "mustard": {
        "h_range": (25, 40),
        "s_range": (100, 200),
        "v_range": (100, 180)
    },
    "khaki": {
        "h_range": (20, 35),
        "s_range": (30, 100),
        "v_range": (150, 220)
    },
    
    # 🟢 Green shades
    "green": {
        "h_range": (35, 85),
        "s_range": (50, 255),
        "v_range": (50, 255)
    },
    "dark_green": {
        "h_range": (35, 85),
        "s_range": (50, 255),
        "v_range": (20, 80)
    },
    "light_green": {
        "h_range": (35, 85),
        "s_range": (30, 150),
        "v_range": (150, 255)
    },
    "olive": {
        "h_range": (35, 65),
        "s_range": (30, 100),
        "v_range": (50, 150)
    },
    "lime": {
        "h_range": (35, 55),
        "s_range": (150, 255),
        "v_range": (150, 255)
    },
    "forest_green": {
        "h_range": (40, 70),
        "s_range": (80, 200),
        "v_range": (30, 100)
    },
    "mint": {
        "h_range": (70, 85),
        "s_range": (30, 100),
        "v_range": (180, 255)
    },
    "teal": {
        "h_range": (75, 95),
        "s_range": (100, 255),
        "v_range": (80, 180)
    },
    
    # 🔵 Blue shades
    "blue": {
        "h_range": (85, 135),
        "s_range": (50, 255),
        "v_range": (50, 255)
    },
    "dark_blue": {
        "h_range": (85, 135),
        "s_range": (50, 255),
        "v_range": (20, 80)
    },
    "light_blue": {
        "h_range": (85, 135),
        "s_range": (30, 150),
        "v_range": (180, 255)
    },
    "navy": {
        "h_range": (95, 125),
        "s_range": (100, 255),
        "v_range": (20, 70)
    },
    "sky_blue": {
        "h_range": (85, 105),
        "s_range": (100, 200),
        "v_range": (180, 255)
    },
    "royal_blue": {
        "h_range": (100, 120),
        "s_range": (150, 255),
        "v_range": (80, 180)
    },
    "cobalt": {
        "h_range": (105, 125),
        "s_range": (150, 255),
        "v_range": (100, 200)
    },
    "turquoise": {
        "h_range": (80, 100),
        "s_range": (100, 200),
        "v_range": (150, 255)
    },
    
    # 🟣 Purple shades
    "purple": {
        "h_range": (125, 165),
        "s_range": (50, 255),
        "v_range": (50, 255)
    },
    "dark_purple": {
        "h_range": (125, 165),
        "s_range": (50, 255),
        "v_range": (20, 80)
    },
    "light_purple": {
        "h_range": (125, 165),
        "s_range": (30, 150),
        "v_range": (180, 255)
    },
    "violet": {
        "h_range": (130, 150),
        "s_range": (100, 255),
        "v_range": (100, 255)
    },
    "lavender": {
        "h_range": (130, 155),
        "s_range": (30, 100),
        "v_range": (180, 255)
    },
    "magenta": {
        "h_range": (145, 165),
        "s_range": (150, 255),
        "v_range": (150, 255)
    },
    "fuchsia": {
        "h_range": (150, 165),
        "s_range": (200, 255),
        "v_range": (150, 255)
    },
    "plum": {
        "h_range": (140, 160),
        "s_range": (100, 200),
        "v_range": (80, 180)
    },
    
    # 🟤 Brown shades
    "brown": {
        "h_range": (0, 25),
        "s_range": (50, 150),
        "v_range": (30, 120)
    },
    "dark_brown": {
        "h_range": (0, 25),
        "s_range": (50, 150),
        "v_range": (15, 60)
    },
    "light_brown": {
        "h_range": (0, 25),
        "s_range": (30, 100),
        "v_range": (100, 180)
    },
    "tan": {
        "h_range": (15, 35),
        "s_range": (30, 80),
        "v_range": (120, 200)
    },
    "beige": {
        "h_range": (20, 40),
        "s_range": (20, 60),
        "v_range": (180, 255)
    },
    "camel": {
        "h_range": (20, 35),
        "s_range": (40, 100),
        "v_range": (100, 180)
    },
    
    # 🩷 Pink shades
    "pink": {
        "h_range": (160, 180),
        "s_range": (50, 255),
        "v_range": (150, 255)
    },
    "light_pink": {
        "h_range": (160, 180),
        "s_range": (30, 150),
        "v_range": (200, 255)
    },
    "hot_pink": {
        "h_range": (165, 180),
        "s_range": (150, 255),
        "v_range": (150, 255)
    },
    "rose": {
        "h_range": (165, 180),
        "s_range": (100, 200),
        "v_range": (120, 200)
    },
    "salmon": {
        "h_range": (0, 15),
        "s_range": (100, 200),
        "v_range": (150, 255)
    },
    
    # ⚫⚪ Gray/Black/White shades
    "black": {
        "h_range": (0, 180),
        "s_range": (0, 50),
        "v_range": (0, 40)
    },
    "dark_gray": {
        "h_range": (0, 180),
        "s_range": (0, 30),
        "v_range": (40, 100)
    },
    "gray": {
        "h_range": (0, 180),
        "s_range": (0, 30),
        "v_range": (100, 180)
    },
    "light_gray": {
        "h_range": (0, 180),
        "s_range": (0, 30),
        "v_range": (180, 220)
    },
    "white": {
        "h_range": (0, 180),
        "s_range": (0, 30),
        "v_range": (220, 255)
    },
    "silver": {
        "h_range": (0, 180),
        "s_range": (0, 20),
        "v_range": (180, 230)
    },
}

# ============================================
# 🎯 การจัดกลุ่มสี (Color Groups) - สำหรับการค้นหา
# ============================================

COLOR_GROUPS = {
    # กลุ่มตามโทนหลัก
    "red_tones": ["red", "dark_red", "crimson", "scarlet", "maroon", "pink", "hot_pink", "rose", "salmon"],
    "orange_tones": ["orange", "dark_orange", "amber", "peach", "coral", "gold", "mustard", "khaki"],
    "yellow_tones": ["yellow", "gold", "light_yellow", "mustard", "khaki", "beige", "tan", "camel"],
    "green_tones": ["green", "dark_green", "light_green", "olive", "lime", "forest_green", "mint", "teal"],
    "blue_tones": ["blue", "dark_blue", "light_blue", "navy", "sky_blue", "royal_blue", "cobalt", "turquoise"],
    "purple_tones": ["purple", "dark_purple", "light_purple", "violet", "lavender", "magenta", "fuchsia", "plum"],
    "brown_tones": ["brown", "dark_brown", "light_brown", "tan", "beige", "camel", "olive", "khaki"],
    "pink_tones": ["pink", "light_pink", "hot_pink", "rose", "salmon", "lavender", "fuchsia"],
    
    # กลุ่มตามความสว่าง
    "light_colors": ["white", "light_gray", "silver", "light_yellow", "light_green", "light_blue", 
                      "light_purple", "light_pink", "sky_blue", "mint", "peach", "beige"],
    "dark_colors": ["black", "dark_gray", "dark_red", "dark_orange", "dark_green", "dark_blue", 
                    "dark_purple", "dark_brown", "navy", "maroon", "forest_green"],
    "medium_colors": ["gray", "red", "orange", "yellow", "green", "blue", "purple", "brown", 
                      "pink", "tan", "camel", "olive", "teal", "turquoise", "violet", "plum"],
    
    # กลุ่มตามความสดใส
    "vibrant_colors": ["red", "orange", "yellow", "green", "blue", "purple", "pink", 
                       "crimson", "scarlet", "amber", "lime", "sky_blue", "royal_blue", 
                       "cobalt", "violet", "magenta", "fuchsia", "hot_pink", "turquoise"],
    "muted_colors": ["gray", "dark_gray", "light_gray", "silver", "olive", "khaki", 
                     "tan", "beige", "camel", "maroon", "navy", "forest_green", "plum"],
    "pastel_colors": ["light_yellow", "light_green", "light_blue", "light_purple", 
                      "light_pink", "mint", "lavender", "peach", "beige"],
    
    # กลุ่มตามอุณหภูมิสี
    "warm_colors": ["red", "orange", "yellow", "pink", "crimson", "scarlet", "amber", 
                    "gold", "peach", "coral", "mustard", "khaki", "brown", "tan", 
                    "beige", "camel", "rose", "salmon", "hot_pink"],
    "cool_colors": ["green", "blue", "purple", "cyan", "teal", "turquoise", "sky_blue", 
                    "royal_blue", "cobalt", "violet", "lavender", "magenta", "fuchsia", 
                    "plum", "mint", "navy", "forest_green"],
    "neutral_colors": ["black", "white", "gray", "dark_gray", "light_gray", "silver", 
                      "beige", "tan", "camel", "khaki"],
    
    # กลุ่มสำหรับเสื้อผ้าที่พบบ่อย
    "common_shirt_colors": ["white", "black", "blue", "gray", "red", "navy", "light_blue", 
                           "pink", "purple", "green", "yellow", "orange", "brown", "beige"],
    "common_pants_colors": ["black", "blue", "gray", "dark_blue", "navy", "brown", "khaki", 
                           "dark_gray", "white", "beige"],
    "formal_colors": ["black", "white", "gray", "dark_gray", "navy", "dark_blue", "brown"],
    "casual_colors": ["blue", "green", "red", "yellow", "orange", "pink", "purple", "teal", 
                     "turquoise", "coral", "mint", "lavender"],
}

# ============================================
# 🔧 ฟังก์ชันช่วยเหลือ - Background Removal
# ============================================

def remove_background_grabcut(img):
    """Fallback: ใช้ GrabCut ตัด Background ออกเพื่อเหลือแต่ Foreground"""
    h, w = img.shape[:2]
    mask = np.ones((h, w), np.uint8) * cv2.GC_PR_FGD
    
    margin_w, margin_h = max(1, int(w * 0.05)), max(1, int(h * 0.05))
    cv2.rectangle(mask, (0, 0), (w-1, h-1), cv2.GC_PR_BGD, margin_w)
    
    mask[0:margin_h, 0:margin_w] = cv2.GC_BGD
    mask[0:margin_h, w-margin_w:w] = cv2.GC_BGD
    
    bgdModel = np.zeros((1, 65), np.float64)
    fgdModel = np.zeros((1, 65), np.float64)
    
    try:
        cv2.grabCut(img, mask, None, bgdModel, fgdModel, 3, cv2.GC_INIT_WITH_MASK)
        return np.where((mask == 2) | (mask == 0), 0, 1).astype(np.uint8)
    except:
        return np.ones(img.shape[:2], dtype=np.uint8)

def get_foreground_mask(img):
    """
    ตัด background ออกและคืนค่า mask
    
    Args:
        img: ภาพ input (BGR)
    
    Returns:
        mask: binary mask (0=background, 1=foreground)
    """
    if REMBG_AVAILABLE:
        try:
            bg_removed = remove(img)
            alpha = bg_removed[:, :, 3]
            fg_mask = (alpha > 50).astype(np.uint8)
            return fg_mask
        except:
            return remove_background_grabcut(img)
    else:
        return remove_background_grabcut(img)

# ============================================
# 🔧 ฟังก์ชันวิเคราะห์สีละเอียด
# ============================================

def analyze_detailed_colors(image_crop, return_map=False):
    """
    วิเคราะห์สีแบบละเอียด (Detailed Color Analysis)
    สำหรับการ tracking ที่ต้องการความแม่นยำสูง
    พร้อมตัด background ออก
    
    Args:
        image_crop: ภาพ crop ของคน/เสื้อผ้า
        return_map: คืนค่า map ภาพสีหรือไม่
    
    Returns:
        dict: ชื่อสีละเอียดและเปอร์เซ็นต์
    """
    if image_crop is None or image_crop.size == 0:
        return ({}, None) if return_map else {}
    
    h, w = image_crop.shape[:2]
    if h < 20 or w < 20:
        return ({}, None) if return_map else {}
    
    # ย่อภาพเพื่อความเร็ว
    small_img = cv2.resize(image_crop, (64, 64))
    
    # ตัด background
    fg_mask = get_foreground_mask(small_img)
    
    # ดึงเฉพาะ pixel ที่เป็น foreground
    bgr_fg = small_img[fg_mask == 1]
    
    # ถ้าโดนตัดหายเกลี้ยงเพราะสีกลืนกันมาก ให้ใช้ภาพทั้งกรอบแทน
    if len(bgr_fg) < 50:
        bgr_fg = small_img.reshape(-1, 3)
        fg_mask = np.ones((64, 64), dtype=np.uint8)
    
    # แปลงเป็น HSV
    hsv_img = cv2.cvtColor(small_img, cv2.COLOR_BGR2HSV)
    
    # สร้าง mask สำหรับแต่ละสี
    color_counts = {}
    total_pixels = len(bgr_fg)
    
    for color_name, ranges in DETAILED_COLOR_RANGES.items():
        h_min, h_max = ranges["h_range"]
        s_min, s_max = ranges["s_range"]
        v_min, v_max = ranges["v_range"]
        
        # สร้าง mask
        mask = cv2.inRange(hsv_img, 
                          (h_min, s_min, v_min), 
                          (h_max, s_max, v_max))
        
        # นับเฉพาะ pixel ที่เป็น foreground
        count = cv2.countNonZero(cv2.bitwise_and(mask, mask, mask=fg_mask))
        
        if count > 0:
            pct = (count / total_pixels) * 100
            if pct > 2.0:  # กรอง noise
                color_counts[color_name] = round(pct, 1)
    
    if return_map:
        # สร้าง map ภาพสี
        map_img = np.zeros((64, 64, 3), dtype=np.uint8)
        
        for color_name, ranges in DETAILED_COLOR_RANGES.items():
            if color_name in color_counts:
                h_min, h_max = ranges["h_range"]
                s_min, s_max = ranges["s_range"]
                v_min, v_max = ranges["v_range"]
                
                mask = cv2.inRange(hsv_img, 
                                  (h_min, s_min, v_min), 
                                  (h_max, s_max, v_max))
                
                # ใส่สีเฉลี่ย
                avg_h = (h_min + h_max) // 2
                avg_s = (s_min + s_max) // 2
                avg_v = (v_min + v_max) // 2
                
                color = cv2.cvtColor(np.array([[[avg_h, avg_s, avg_v]]], dtype=np.uint8), 
                                   cv2.COLOR_HSV2BGR)[0][0]
                
                map_img[mask > 0] = color
        
        return color_counts, map_img
    
    return color_counts

def get_color_groups(detailed_colors):
    """
    แปลงสีละเอียดเป็นกลุ่มสี
    สำหรับการค้นหาที่ต้องการความกว้างขวาง
    
    Args:
        detailed_colors: dict ของสีละเอียดจาก analyze_detailed_colors
    
    Returns:
        dict: กลุ่มสีที่ตรงกับสีละเอียด
    """
    detected_groups = {}
    
    for group_name, group_colors in COLOR_GROUPS.items():
        # ตรวจสอบว่ามีสีในกลุ่มนี้ไหม
        matched_colors = [c for c in group_colors if c in detailed_colors]
        
        if matched_colors:
            # คำนวณ total percentage ของกลุ่ม
            total_pct = sum(detailed_colors[c] for c in matched_colors)
            if total_pct > 5.0:  # กรองกลุ่มที่น้อยเกินไป
                detected_groups[group_name] = {
                    "colors": matched_colors,
                    "percentage": round(total_pct, 1),
                    "individual": {c: detailed_colors[c] for c in matched_colors}
                }
    
    return detected_groups

def get_primary_detailed_color(detailed_colors):
    """
    หาสีละเอียดหลัก (Primary Detailed Color)
    
    Args:
        detailed_colors: dict ของสีละเอียด
    
    Returns:
        str: ชื่อสีละเอียดที่มีเปอร์เซ็นต์สูงสุด
    """
    if not detailed_colors:
        return "unknown"
    
    return max(detailed_colors, key=detailed_colors.get)

def get_primary_color_group(color_groups):
    """
    หากลุ่มสีหลัก (Primary Color Group)
    
    Args:
        color_groups: dict ของกลุ่มสีจาก get_color_groups
    
    Returns:
        str: ชื่อกลุ่มสีที่มีเปอร์เซ็นต์สูงสุด
    """
    if not color_groups:
        return "unknown"
    
    return max(color_groups, key=lambda x: color_groups[x]["percentage"])

def search_by_color_group(track_history, group_name, min_percentage=10.0):
    """
    ค้นหาคนตามกลุ่มสี
    
    Args:
        track_history: dict ของข้อมูล tracking
        group_name: ชื่อกลุ่มสีที่ต้องการค้นหา
        min_percentage: เปอร์เซ็นต์ขั้นต่ำ
    
    Returns:
        list: รายการ track_id ที่ตรงกับเงื่อนไข
    """
    results = []
    
    for track_id, data in track_history.items():
        if "color_groups" in data and group_name in data["color_groups"]:
            group_data = data["color_groups"][group_name]
            if group_data["percentage"] >= min_percentage:
                results.append({
                    "track_id": track_id,
                    "percentage": group_data["percentage"],
                    "colors": group_data["colors"],
                    **data
                })
    
    return results

def search_by_detailed_color(track_history, color_name, min_percentage=5.0):
    """
    ค้นหาคนตามสีละเอียด
    
    Args:
        track_history: dict ของข้อมูล tracking
        color_name: ชื่อสีละเอียดที่ต้องการค้นหา
        min_percentage: เปอร์เซ็นต์ขั้นต่ำ
    
    Returns:
        list: รายการ track_id ที่ตรงกับเงื่อนไข
    """
    results = []
    
    for track_id, data in track_history.items():
        if "detailed_colors" in data and color_name in data["detailed_colors"]:
            if data["detailed_colors"][color_name] >= min_percentage:
                results.append({
                    "track_id": track_id,
                    "percentage": data["detailed_colors"][color_name],
                    **data
                })
    
    return results

# ============================================
# 🎨 ฟังก์ชันช่วยเหลือเพิ่มเติม
# ============================================

def get_all_detailed_colors():
    """คืนค่ารายชื่อสีละเอียดทั้งหมด"""
    return list(DETAILED_COLOR_RANGES.keys())

def get_all_color_groups():
    """คืนค่ารายชื่อกลุ่มสีทั้งหมด"""
    return list(COLOR_GROUPS.keys())

def get_color_group_members(group_name):
    """คืนค่าสมาชิกของกลุ่มสี"""
    return COLOR_GROUPS.get(group_name, [])

def is_color_in_group(color_name, group_name):
    """ตรวจสอบว่าสีอยู่ในกลุ่มที่ระบุหรือไม่"""
    return color_name in COLOR_GROUPS.get(group_name, [])

if __name__ == "__main__":
    # ทดสอบระบบ
    print("🎨 Detailed Color System")
    print(f"Total detailed colors: {len(DETAILED_COLOR_RANGES)}")
    print(f"Total color groups: {len(COLOR_GROUPS)}")
    print(f"\nDetailed colors: {get_all_detailed_colors()}")
    print(f"\nColor groups: {get_all_color_groups()}")
