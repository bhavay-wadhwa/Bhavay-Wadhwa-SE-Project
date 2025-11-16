"""
stereo_depth.py
Basic stereo disparity -> depth helper using OpenCV.
Requires:
  - calibrated & rectified stereo image pair
  - camera baseline (meters) and focal length (pixels)

Usage:
  from distance_methods.stereo_depth import disparity_to_depth, estimate_bbox_depth
"""

import numpy as np

def disparity_to_depth(disparity_px: float, focal_length_px: float, baseline_m: float) -> float:
    """
    Convert disparity (pixels) to depth (meters):
        depth = (focal_length_px * baseline_m) / disparity_px
    """
    if disparity_px <= 0:
        return float("inf")
    return (focal_length_px * baseline_m) / float(disparity_px)

def estimate_bbox_depth(disparity_map: np.ndarray, bbox: tuple, focal_length_px: float, baseline_m: float, method: str = "median"):
    """
    Estimate object depth from disparity map inside bbox.
    bbox = (x1,y1,x2,y2)
    method = 'median' or 'mean'
    Returns meters
    """
    x1,y1,x2,y2 = bbox
    # ensure integers & bounds
    h, w = disparity_map.shape[:2]
    x1 = max(0, int(round(x1)))
    x2 = min(w-1, int(round(x2)))
    y1 = max(0, int(round(y1)))
    y2 = min(h-1, int(round(y2)))
    if x2 <= x1 or y2 <= y1:
        return float("inf")

    crop = disparity_map[y1:y2+1, x1:x2+1].astype(float)
    # mask invalid disparities (<=0)
    crop = crop[crop > 0]
    if crop.size == 0:
        return float("inf")

    disp = np.median(crop) if method == "median" else np.mean(crop)
    return disparity_to_depth(disp, focal_length_px, baseline_m)
