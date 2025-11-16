"""
bbox_pixel_method.py
Fit a simple inverse model: distance ~= a / bbox_height_px + b
Use calibrations to compute a and b or set defaults.

Usage:
    from distance_methods.bbox_pixel_method import estimate_distance, fit_model
"""

from typing import Tuple
import numpy as np

# Default coefficients (weak generic fallback) - you should fit these per camera
DEFAULT_COEFFS = (500.0, 0.0)  # a, b

def estimate_distance(bbox_height_px: float, coeffs: Tuple[float,float] = DEFAULT_COEFFS) -> float:
    a, b = coeffs
    if bbox_height_px <= 0:
        return float("inf")
    return float(a / float(bbox_height_px) + b)

def fit_model(pixel_heights: np.ndarray, true_distances: np.ndarray) -> Tuple[float,float]:
    """
    Fit a simple inverse linear model distance = a / h + b using least squares.
    pixel_heights: array of bbox heights in px
    true_distances: corresponding true distances in meters
    Returns coefficients (a, b)
    """
    # transform: y = a * (1/h) + b  --> linear regression on x = (1/h)
    X = np.vstack([1.0 / pixel_heights, np.ones_like(pixel_heights)]).T
    y = true_distances
    params, *_ = np.linalg.lstsq(X, y, rcond=None)
    a, b = params[0], params[1]
    return float(a), float(b)
