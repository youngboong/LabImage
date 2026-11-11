"""Dev-only: before/after crops (baseline | learned out-of-fold) of the traced GT tubes. GT magenta, trace yellow.

    .venv/Scripts/python.exe scripts/cnt_crops.py NAME... [--waypoints 0] [--out validation/cnt-learn/crops]
"""
import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

import cnt_detect
from cnt_eval import discover, evaluate


def draw(rgb, gt, traces, box):
    canvas = rgb.copy()
    for tube in gt:
        if tube['certain']: cv2.polylines(canvas, [np.rint(tube['path']).astype(np.int32)], False, (255, 0, 255), 3)
    for path in traces: cv2.polylines(canvas, [np.rint(path).astype(np.int32)], False, (255, 255, 0), 1)
    x0, y0, x1, y1 = box
    return cv2.resize(canvas[y0:y1, x0:x1], None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('names', nargs='+')
    ap.add_argument('--waypoints', type=int, default=0)
    ap.add_argument('--out', default='validation/cnt-learn/crops')
    ap.add_argument('--oof-dir', default='validation/cnt-learn/oof')
    ap.add_argument('--learned-weight', type=float, default=None)
    ap.add_argument('--turn', type=float, default=None)
    a = ap.parse_args()
    if a.learned_weight is not None: cnt_detect.TRACK_LEARNED = a.learned_weight
    if a.turn is not None: cnt_detect.TRACK_TURN = a.turn
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    images, _ = discover(['CNT/261103', 'CNT/261105'], 0, set(a.names))
    for image in images:
        runs = [evaluate(image, (a.waypoints,), m, a.oof_dir) for m in ('none', 'oof')]
        pts = np.vstack([t['path'] for t in runs[0]['gt'] if t['certain']])
        h, w = runs[0]['rgb'].shape[:2]
        x0, y0 = np.maximum(pts.min(0)-40, 0).astype(int); x1, y1 = np.minimum(pts.max(0)+40, [w, h]).astype(int)
        box = (x0, y0, max(x1, x0+80), max(y1, y0+80))
        panels = [draw(r['rgb'], r['gt'], r['traces'][a.waypoints], box) for r in runs]
        sym = [np.median([x['sym_dist'] for x in r['rows'] if x['sym_dist'] is not None]) for r in runs]
        for p, label in zip(panels, (f'baseline sym median {sym[0]:.1f}px', f'learned (OOF) sym median {sym[1]:.1f}px')):
            cv2.putText(p, label, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 255, 0), 2)
        Image.fromarray(np.hstack(panels)).save(out/f"{image['base'].stem}_w{a.waypoints}.png")
        print(image['base'].stem, 'baseline', round(sym[0], 2), 'learned', round(sym[1], 2), flush=True)


if __name__ == '__main__':
    main()
