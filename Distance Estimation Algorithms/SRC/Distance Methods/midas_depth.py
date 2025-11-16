"""
midas_depth.py
Wrapper for MiDaS monocular depth estimation.
Note: MiDaS produces relative depth values; a scale alignment to real distances is required.

Usage:
    from distance_methods.midas_depth import MiDaSDepth
    model = MiDaSDepth(device='cuda')
    depth_map = model.predict(image)  # depth_map: HxW floats
    # estimate bbox distance: take median depth within bbox (then scale)
"""

import numpy as np

class MiDaSDepth:
    def __init__(self, model_type="DPT_Large", device="cpu"):
        """
        Lazy import to avoid heavy dependencies unless used.
        model_type: "DPT_Large", "DPT_Hybrid", "MiDaS_small"
        """
        self.device = device
        self.model_type = model_type
        try:
            import torch
            from torchvision.transforms import Compose
            # MiDaS installation and model loading
            from midas.midas_net import MidasNet  # if using local packaged midas
            # Many users will prefer to use official MiDaS repo code. This is a placeholder wrapper.
            self._torch = torch
            self.model = None
        except Exception as e:
            raise RuntimeError("MiDaS dependencies not found. Install from https://github.com/intel-isl/MiDaS and follow instructions.") from e

    def predict(self, image_bgr: np.ndarray) -> np.ndarray:
        """
        Run inference and return depth map (H x W) as floats. Implementation depends on MiDaS setup.
        For simplicity, raise NotImplementedError if MiDaS not configured.
        """
        raise NotImplementedError("MiDaS wrapper requires installation from MiDaS repo. See docs: https://github.com/intel-isl/MiDaS")
    
    @staticmethod
    def median_depth_in_bbox(depth_map: np.ndarray, bbox: tuple):
        x1,y1,x2,y2 = bbox
        h, w = depth_map.shape[:2]
        x1 = max(0, int(round(x1)))
        x2 = min(w-1, int(round(x2)))
        y1 = max(0, int(round(y1)))
        y2 = min(h-1, int(round(y2)))
        if x2 <= x1 or y2 <= y1:
            return float("nan")
        crop = depth_map[y1:y2+1, x1:x2+1]
        crop = crop[np.isfinite(crop)]
        if crop.size == 0:
            return float("nan")
        return float(np.median(crop))
