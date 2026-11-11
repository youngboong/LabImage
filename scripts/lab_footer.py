"""Detect a separate, full-width microscope information strip conservatively."""
import cv2
import numpy as np


def detect_information_footer(gray):
    height, width = gray.shape
    if height < 64 or width < 128:
        return height
    # A footer has a nearly uniform background interrupted by text and rules.
    # Require a boundary from textured image content, and text-sized components
    # below it, so ordinary dark image regions are not automatically cropped.
    row_std = gray.std(axis=1)
    flat = (np.abs(gray.astype(np.float32)-np.median(gray,axis=1)[:,None]) <= 5).mean(axis=1) >= .97
    for y in range(max(32, int(height*.60)), height-15):
        # Smooth substrates sit above the bar too: a uniform rule row that differs from the row above counts as the boundary.
        rule = row_std[y] < 1 and abs(float(np.median(gray[y]))-float(np.median(gray[y-1]))) > 10
        if not flat[y:y+2].all() or (np.mean(row_std[y-10:y]) < 10 and not rule):
            continue
        strip = gray[y:]
        background = int(np.bincount(strip.ravel(), minlength=256).argmax())
        foreground = (np.abs(strip.astype(np.int16)-background) > 18).astype(np.uint8)
        if foreground.mean() > .32:
            continue
        _, _, stats, _ = cv2.connectedComponentsWithStats(foreground)
        letters = [s for s in stats[1:] if 2 <= s[2] <= width*.06
                   and 4 <= s[3] <= min(60, strip.shape[0]*.65) and s[4] >= 6]
        if len(letters) >= 8 and np.ptp([s[0] for s in letters]) > width*.15:
            return y
    return height
