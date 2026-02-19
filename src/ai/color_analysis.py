import cv2
import numpy as np
from collections import Counter

# 🎨 กำหนด Palette สีมาตรฐาน (RGB)
# คุณสามารถเพิ่ม/ลดสีตรงนี้ได้ตามใจชอบ
COLOR_PALETTE = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "grey": (128, 128, 128),
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255), # สีชมพูเข้ม/ม่วง
    "orange": (255, 165, 0),
    "purple": (128, 0, 128),
    "brown": (165, 42, 42)
}

def get_closest_color(pixel):
    """หาว่า Pixel นี้ใกล้เคียงกับสีไหนใน Palette ที่สุด"""
    min_dist = float("inf")
    closest_name = "unknown"
    
    # คำนวณ Euclidean distance
    for name, rgb in COLOR_PALETTE.items():
        dist = np.linalg.norm(np.array(pixel) - np.array(rgb))
        if dist < min_dist:
            min_dist = dist
            closest_name = name
    return closest_name

def analyze_color_histogram(image_crop):
    """
    รับรูป Crop (numpy array) -> คืนค่า % สีเป็น Dictionary
    Example Output: {"red": 60.5, "black": 30.0, "white": 9.5}
    """
    if image_crop is None or image_crop.size == 0:
        return {}

    # 1. ย่อภาพให้เล็กมาก เพื่อให้คำนวณไวๆ (เช่น 50x50 pixels)
    # ไม่จำเป็นต้องใช้ภาพชัดระดับ 4K เพื่อหาสี
    small_img = cv2.resize(image_crop, (50, 50))
    
    # 2. แปลงสี BGR (OpenCV) -> RGB
    img_rgb = cv2.cvtColor(small_img, cv2.COLOR_BGR2RGB)
    
    # 3. Reshape เป็นลิสต์ของ Pixels (2500, 3)
    pixels = img_rgb.reshape(-1, 3)
    
    # 4. วนลูปนับสี (ขั้นตอนนี้ถ้าภาพใหญ่จะช้า เราถึงต้องย่อภาพก่อน)
    color_counts = Counter()
    for pixel in pixels:
        color_name = get_closest_color(pixel)
        color_counts[color_name] += 1
        
    # 5. คำนวณเป็น %
    total_pixels = len(pixels)
    color_profile = {}
    
    for color, count in color_counts.items():
        percentage = round((count / total_pixels) * 100, 1)
        if percentage > 5.0: # เก็บเฉพาะสีที่มีมากกว่า 5% (กรอง Noise)
            color_profile[color] = percentage
            
    return color_profile