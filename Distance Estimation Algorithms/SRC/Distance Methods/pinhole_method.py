"""
pinhole_method.py
Estimate distance using Pinhole Camera Model:
    distance = (object_real_height_m * focal_length_px) / bbox_height_px

Usage:
    from distance_methods.pinhole_method import estimate_distance
    d = estimate_distance(bbox_height_px, object_class='person', camera_params=camera_params)
"""

from typing import Dict

# default average heights (meters) per class
DEFAULT_OBJECT_HEIGHTS = {
    "person": 1.7,
    "car": 1.5,
    "truck": 3.0,
    "motorbike": 1.1,
}

def estimate_distance(bbox_height_px: float,
                      object_class: str = "person",
                      camera_params: Dict[str, float] = None) -> float:
    """
    Estimate distance using a simple pinhole model.

    Args:
        bbox_height_px: bounding box height in pixels
        object_class: string key for object height lookup
        camera_params: dict with keys { 'focal_length_px': float, 'camera_height_m': float (optional) }

    Returns:
        distance_m: estimated distance in meters (approx)
    """
    if bbox_height_px <= 0:
        return float("inf")

    if camera_params is None:
        raise ValueError("camera_params must include 'focal_length_px' (pixels).")

    f = camera_params.get("focal_length_px")
    if f is None:
        raise ValueError("camera_params must contain 'focal_length_px' (in pixels).")

    H = DEFAULT_OBJECT_HEIGHTS.get(object_class, DEFAULT_OBJECT_HEIGHTS["person"])

    distance_m = (H * f) / float(bbox_height_px)
    return float(distance_m)


# Example helper: compute focal length px from calibration data
def focal_length_px_from_fov(image_height_px: int, vertical_fov_deg: float) -> float:
    """
    Approximate focal length in pixels from vertical field-of-view:
    f = (image_height_px / 2) / tan(vfov/2)
    """
    import math
    vfov_rad = math.radians(vertical_fov_deg)
    return (image_height_px / 2.0) / math.tan(vfov_rad / 2.0)
