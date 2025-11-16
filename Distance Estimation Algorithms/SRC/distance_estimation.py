"""
distance_estimation.py

Provides unified API to estimate distance for a bounding box using selected method.
"""

from typing import Tuple, Dict

# Import methods
from distance_methods.pinhole_method import estimate_distance as pinhole_estimate
from distance_methods.bbox_pixel_method import estimate_distance as bbox_estimate
from distance_methods.stereo_depth import estimate_bbox_depth as stereo_estimate
# MiDaS optional import is lazy
# from distance_methods.midas_depth import MiDaSDepth

def estimate_distance_for_bbox(method: str, bbox: Tuple[int,int,int,int], *,
                               image=None,  # needed for some methods like MiDaS
                               class_name: str = "person",
                               camera_params: Dict = None,
                               bbox_height_px: float = None,
                               disparity_map=None,
                               stereo_params: Dict = None) -> float:
    """
    Unified function to estimate distance for a single bounding box.

    Args:
        method: 'pinhole', 'bbox', 'stereo', 'midas'
        bbox: (x1,y1,x2,y2)
        image: full image (required for midas)
        class_name: object class (used by pinhole)
        camera_params: dict with keys like 'focal_length_px'
        bbox_height_px: precomputed bbox height in pixels (optional)
        disparity_map: for stereo method
        stereo_params: dict with 'focal_length_px', 'baseline_m'

    Returns:
        distance in meters (float). inf on failure.
    """
    x1,y1,x2,y2 = bbox
    if bbox_height_px is None:
        bbox_height_px = max(1, y2 - y1)

    if method == "pinhole":
        return pinhole_estimate(bbox_height_px, object_class=class_name, camera_params=camera_params)
    elif method == "bbox":
        coeffs = camera_params.get("bbox_coeffs") if camera_params else None
        if coeffs is None:
            from distance_methods.bbox_pixel_method import DEFAULT_COEFFS
            coeffs = DEFAULT_COEFFS
        return bbox_estimate(bbox_height_px, coeffs=coeffs)
    elif method == "stereo":
        if disparity_map is None or stereo_params is None:
            return float("inf")
        focal = stereo_params.get("focal_length_px")
        baseline = stereo_params.get("baseline_m")
        from distance_methods.stereo_depth import estimate_bbox_depth
        return estimate_bbox_depth(disparity_map, bbox, focal, baseline, method="median")
    elif method == "midas":
        # placeholder, user must construct MiDaSDepth and call predict
        try:
            from distance_methods.midas_depth import MiDaSDepth
            model = MiDaSDepth(device=camera_params.get("device","cpu"))
            depth_map = model.predict(image)
            return MiDaSDepth.median_depth_in_bbox(depth_map, bbox)
        except Exception:
            return float("inf")
    else:
        raise ValueError(f"Unknown distance estimation method: {method}")
