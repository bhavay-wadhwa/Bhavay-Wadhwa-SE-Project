"""
Quick test script to validate methods (non-exhaustive).
Run: python src/test_distance_methods.py
"""

import numpy as np
from distance_methods.pinhole_method import focal_length_px_from_fov, estimate_distance as pinhole
from distance_methods.bbox_pixel_method import fit_model, estimate_distance as bbox_est
from distance_methods.stereo_depth import disparity_to_depth

def test_pinhole():
    # suppose image height 720, vfov 49 deg -> compute f
    f = focal_length_px_from_fov(720, 49.0)
    camera_params = {"focal_length_px": f}
    # person bbox height 200 px
    d = pinhole(200, object_class="person", camera_params=camera_params)
    print("Pinhole estimate:", d)

def test_bbox_fit():
    # synthetic calibration: pixel heights and ground truths
    heights = np.array([300, 250, 200, 150, 100], dtype=float)
    dists = np.array([5.0, 6.5, 8.0, 11.0, 18.0], dtype=float)
    a,b = fit_model(heights, dists)
    print("Fitted coeffs:", a, b)
    print("Estimate for 200 px:", bbox_est(200, coeffs=(a,b)))

def test_stereo():
    f_px = 1200.0
    baseline_m = 0.12
    disp = 60.0
    print("Stereo depth:", disparity_to_depth(disp, f_px, baseline_m))

if __name__ == "__main__":
    test_pinhole()
    test_bbox_fit()
    test_stereo()
