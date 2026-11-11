"""Dev-only evaluation of CNT trace measurement against the user's yellow labels.

    .venv/Scripts/python.exe scripts/cnt_eval.py [--model auto|none|oof] [--folds validation/cnt-learn/folds.json]
        [--waypoints 0 1 2] [--learned-weight L] [--turn T] [--images NAME ...] [--out validation/cnt-eval]
        [--stroke [--stroke-amp A] [--seed N]]   (validation/cnt-stroke; click results at 0 and 2 waypoints are rerun beside it)

Length ground truth comes from X(2).tif (yellow polylines); width (only with --width) from X(3).tif.
Each certain GT tube is traced between its two tips (simulating two clicks, plus interior waypoints) and
compared by mean symmetric distance. Only images allowed by `eligible` are used. Exit code is 0 even
on FAIL: this is a report, not a test.

--stroke simulates a hand drag per GT tube (`hand_stroke`) and traces it with cnt_detect.trace_stroke.
"""
import argparse
import csv
import json
import re
import time
import zlib
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.graph import MCP_Geometric
from skimage.measure import approximate_polygon
from skimage.morphology import skeletonize

import cnt_detect
from cnt_detect import measure_spot, resample, ridge_response, trace_stroke, trace_tube, width_at
from lab_footer import detect_information_footer

FOV_UM_AT_1KX, IMAGE_WIDTH_PX = 279.0, 1024


def luminance(path): return np.asarray(Image.open(path).convert('L'))


def yellow(path, bottom):
    rgb = np.asarray(Image.open(path).convert('RGB')).astype(int)[:bottom]
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (r > 150) & (g > 150) & (b < 110) & (np.minimum(r, g)-b > 60)


def gt_tubes(path, bottom, width):
    """Simple (2-tip) GT polylines, plus the count of complex ones."""
    labels, _ = ndi.label(yellow(path, bottom), np.ones((3, 3)))
    simple, complex_count = [], 0
    for index, box in enumerate(ndi.find_objects(labels), 1):
        h, w = box[0].stop-box[0].start, box[1].stop-box[1].start
        if max(h, w) < 60: continue  # text glyphs are smaller
        comp = labels == index
        skeleton = skeletonize(comp)
        neighbours = ndi.convolve(skeleton.astype(int), np.ones((3, 3)), mode='constant')-1
        tips = np.argwhere(skeleton & (neighbours == 1))
        if len(tips) != 2:
            complex_count += 1; continue
        solver = MCP_Geometric(np.where(skeleton, 1., np.inf), fully_connected=True)
        solver.find_costs([tuple(tips[0])], [tuple(tips[1])])
        rc = np.asarray(solver.traceback(tuple(tips[1])), float)
        xy = rc[:, ::-1]
        length = float(np.linalg.norm(np.diff(approximate_polygon(xy, 1.5), axis=0), axis=1).sum())
        edge = 5 <= box[0].start and 5 <= box[1].start and box[0].stop <= bottom-5 and box[1].stop <= width-5
        simple.append(dict(tips=tips[:, ::-1].astype(float), path=xy, length=length, certain=length >= 60 and edge))
    return simple, complex_count


def gt_widths(path, bottom):
    labels, _ = ndi.label(yellow(path, bottom), np.ones((3, 3)))
    segments = []
    for index, box in enumerate(ndi.find_objects(labels), 1):
        if max(box[0].stop-box[0].start, box[1].stop-box[1].start) < 25: continue
        yy, xx = np.nonzero(labels[box] == index)
        pts = np.column_stack([xx+box[1].start, yy+box[0].start]).astype(float)
        center = pts.mean(0)
        _, s, vt = np.linalg.svd(pts-center)
        if s[1]/max(s[0], 1e-9) > .15: continue  # not line-like
        segments.append(dict(c=center, d=vt[0], L=float(np.ptp((pts-center)@vt[0]))))
    marks, used = [], set()
    for i, a in enumerate(segments):
        best = None
        for j, b in enumerate(segments):
            if j <= i or i in used or j in used: continue
            if abs(a['d']@b['d']) < .98 or abs(a['L']-b['L']) > .2*max(a['L'], b['L']): continue
            normal, offset = np.array([-a['d'][1], a['d'][0]]), b['c']-a['c']
            perpendicular = abs(offset@normal)
            if abs(offset@a['d']) > .5*a['L'] or perpendicular > 150: continue
            if best is None or perpendicular < best[0]: best = (perpendicular, j)
        if best:
            used |= {i, best[1]}
            marks.append(dict(mid=(a['c']+segments[best[1]]['c'])/2, tangent=a['d'], width=best[0]))
    return marks


def matches(candidate_path, gt_path, width_px):
    tol = max(6., .75*(width_px or 16.))
    a, b = resample(candidate_path), resample(gt_path)
    return (cKDTree(a).query(b)[0] <= tol).mean() >= .7 and (cKDTree(b).query(a)[0] <= tol).mean() >= .7


def stats(values):
    v = np.asarray([x for x in values if x is not None and np.isfinite(x)], float)
    if not len(v): return dict(n=0, median_abs=np.nan, p90_abs=np.nan, bias=np.nan)
    return dict(n=len(v), median_abs=float(np.median(np.abs(v))), p90_abs=float(np.percentile(np.abs(v), 90)), bias=float(np.median(v)))


def eligible(folder, stem):
    """User's data rule: all of 261105; 261103 only images numbered -<n> with n <= 29 (unnumbered and 30+ are out)."""
    if str(folder).replace('\\', '/').rstrip('/').endswith('261105'): return True
    m = re.search(r'-(\d+)$', stem)
    return bool(m) and int(m[1]) <= 29


def mag_bin(mag):
    return '<300x' if mag < 300 else '300-800x' if mag < 1000 else '>=1kx'


BINS = ('<300x', '300-800x', '>=1kx')


def discover(folders, min_mag, names):
    found, skipped = [], []
    for folder in folders:
        files = {f.name.lower(): f for f in Path(folder).iterdir()}
        for lower, f2 in sorted(files.items()):
            if not lower.endswith('(2).tif'): continue
            base = files.get(lower.replace('(2)', '', 1))
            if base is None: skipped.append(f'{f2.name}: no base image'); continue
            if names and base.name not in names and base.stem not in names: continue
            if not eligible(folder, base.stem): skipped.append(f'{base.name}: excluded by rule'); continue
            m = re.search(r'_(\d+(?:\.\d+)?)(k?)x', base.name)
            if not m: skipped.append(f'{base.name}: no magnification in name'); continue
            mag = float(m.group(1))*(1000 if m.group(2) else 1)
            if mag < min_mag: skipped.append(f'{base.name}: {mag:g}x below {min_mag:g}x'); continue
            found.append(dict(base=base, two=f2, three=files.get(lower.replace('(2)', '(3)', 1)), mag=mag))
    return found, skipped


def sym_dist(a, b):
    """0.5*(mean NN distance a->b + mean NN distance b->a) on 1-px resampled paths."""
    a, b = resample(a), resample(b)
    return float(.5*(cKDTree(b).query(a)[0].mean()+cKDTree(a).query(b)[0].mean()))


def overlay(rgb, gt, marks, traces, out, color=(255, 0, 255)):
    canvas = rgb.copy()
    for tube in gt: cv2.polylines(canvas, [np.rint(tube['path']).astype(np.int32)], False, (255, 230, 0), 2)
    for mark in marks:
        n = np.array([-mark['tangent'][1], mark['tangent'][0]])
        cv2.line(canvas, *[tuple(np.rint(mark['mid']+s*n*mark['width']/2).astype(int)) for s in (-1, 1)], (255, 140, 0), 2)
    for index, path in enumerate(traces):
        cv2.polylines(canvas, [np.rint(path).astype(np.int32)], False, color, 1)
        cv2.putText(canvas, str(index), tuple(np.rint(path[len(path)//2]).astype(int)), cv2.FONT_HERSHEY_SIMPLEX, .6, color, 2)
    Image.fromarray(canvas).save(out)


STROKE_AMP = .25              # lateral wander of a simulated drag: std = 0.25 x tube width, smooth over ~one width (peak <= 2.5 std)
STROKE_END_PX = 5.             # each end of the drag is trimmed or extended along the tube by U(-5, 5) px, plus N(0, 1.5) px sideways
STROKE_STEP_PX = (4., 8.)      # spacing of the sampled 'mouse' points along the drag, px; plus N(0, 1) px of jitter


def hand_stroke(path, width, rng, shape, amp=STROKE_AMP):
    """A simulated freehand drag along a GT path: smooth lateral wander, end offsets, mouse-like sampling, clipped to the image."""
    p = resample(path)
    t = np.gradient(ndi.gaussian_filter1d(p, 3, axis=0, mode='nearest'), axis=0)
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
    noise = ndi.gaussian_filter1d(rng.normal(size=len(p)), max(width/2, 2.), mode='nearest')
    noise = np.clip(noise/max(float(noise.std()), 1e-9), -2.5, 2.5)
    p = p+(amp*width*noise)[:, None]*np.column_stack([-t[:, 1], t[:, 0]])
    for end in (0, 1):
        delta = rng.uniform(-STROKE_END_PX, STROKE_END_PX)       # > 0 extends beyond the GT end, < 0 trims
        e, u = (p[0], -t[0]) if end == 0 else (p[-1], t[-1])
        tail = e+np.outer(np.arange(1, int(delta)+1), u) if delta >= 0 else np.empty((0, 2))
        if delta < 0: p = p[int(-delta):] if end == 0 else p[:len(p)+int(delta)]
        side = rng.normal(0, 1.5)*np.array([-u[1], u[0]])
        if end == 0: p = np.vstack([tail[::-1], p]); p[0] += side
        else: p = np.vstack([p, tail]); p[-1] += side
    arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    s = [0.]
    while s[-1] < arc[-1]: s.append(s[-1]+rng.uniform(*STROKE_STEP_PX))
    s[-1] = arc[-1]
    q = np.column_stack([np.interp(s, arc, p[:, k]) for k in (0, 1)])
    q[1:-1] += rng.normal(0, 1, q[1:-1].shape)
    return np.clip(q, 0, [shape[1]-1, shape[0]-1])


def centerline_for(model, gray, stem, oof_dir):
    if model == 'none': return None
    if model == 'oof': return np.load(Path(oof_dir)/f'{stem}.npy').astype(np.float32)
    return cnt_detect.centerline_map(gray)


def evaluate(image, waypoints=(0,), model='none', oof_dir=None, fold=None, width=False, stroke=None):
    base = luminance(image['base'])
    bottom = detect_information_footer(base)
    gray = base[:bottom]
    ump = FOV_UM_AT_1KX/IMAGE_WIDTH_PX*1000/image['mag']
    started = time.time()
    ridge = ridge_response(gray, ump, True)
    ridge['P'] = centerline_for(model, gray, image['base'].stem, oof_dir)
    gt, complex_count = gt_tubes(image['two'], bottom, gray.shape[1])
    certain = [t for t in gt if t['certain']]
    rows, traces = [], {}
    t0 = time.time()
    for k in waypoints:
        traces[k] = []
        for tube in certain:
            # simulate Shift-click waypoints: interior GT points equally spaced by arc length
            arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(tube['path'], axis=0), axis=1))]
            inner = [tube['path'][int(np.searchsorted(arc, arc[-1]*i/(k+1)))].tolist() for i in range(1, k+1)]
            try: c = trace_tube(gray, ridge, [tube['path'][0].tolist(), *inner, tube['path'][-1].tolist()])
            except ValueError: c = None
            matched = c is not None and matches(c['path'], tube['path'], c['band_px'])
            error = None if c is None else c['length_px']/tube['length']-1
            if c is not None: traces[k].append(c['path'])
            rows.append(dict(kind='length', gt=tube['length'], pred=None if c is None else c['length_px'], error=error, matched=matched,
                             sym_dist=None if c is None else sym_dist(c['path'], tube['path']), waypoints=k, model=model, fold=fold,
                             bin=mag_bin(image['mag']), width_px=None if c is None else c['width_px'],
                             tip_x=tube['tips'][0][0], tip_y=tube['tips'][0][1]))
            if k == waypoints[0]: tube['trace'] = c
    stroke_rows, strokes = [], []
    for n, tube in enumerate(certain if stroke else []):
        rng = np.random.default_rng([stroke['seed'], zlib.crc32(image['base'].stem.encode()), n])
        w = cnt_detect.path_width(gray, ridge, resample(tube['path']))
        hand = hand_stroke(tube['path'], w, rng, gray.shape, stroke['amp'])
        try: c = trace_stroke(gray, ridge, hand)
        except ValueError: c = None
        tip = lambda end: float(np.linalg.norm(tube['tips']-end, axis=1).min())   # distance to the nearer GT tip
        stroke_rows.append(dict(kind='stroke', gt=tube['length'], width=w, bin=mag_bin(image['mag']), stroke_length=float(np.linalg.norm(np.diff(hand, axis=0), axis=1).sum()),
            pred=None if c is None else c['length_px'], error=None if c is None else c['length_px']/tube['length']-1,
            matched=c is not None and matches(c['path'], tube['path'], c['band_px']), sym_dist=None if c is None else sym_dist(c['path'], tube['path']),
            end_shift=None if c is None else c['end_shift'], tip_before=[tip(hand[0]), tip(hand[-1])], tip_after=None if c is None else [tip(c['path'][0]), tip(c['path'][-1])]))
        if c is not None: strokes.append((hand, c['path']))
    marks = gt_widths(image['three'], bottom) if width and image['three'] else []
    for mark in marks:
        r = width_at(gray, mark['mid'], mark['tangent'], ump, True)
        method = None if r is None else r[0]/mark['width']-1
        near = [t['trace'] for t in gt if t.get('trace') is not None
                and cKDTree(t['trace']['path']).query(mark['mid'])[0] <= max(6, mark['width']/2+4) and t['trace']['width_px']]
        reported = near[0]['width_px']/mark['width']-1 if near else None
        # tube-matched: nearest traced tube (looser distance than above) vs the user's D mark; `none` = tube reports no D
        tubes = [(cKDTree(t['trace']['path']).query(mark['mid'])[0], t['trace']) for t in gt if t.get('trace') is not None]
        tubes = [(d, c) for d, c in tubes if d <= max(10, mark['width'])]
        matched_tube = min(tubes, key=lambda x: x[0])[1] if tubes else None
        tube_error = matched_tube['width_px']/mark['width']-1 if matched_tube and matched_tube['width_px'] else None
        try: spot = measure_spot(gray, ridge, mark['mid'])  # Width-only: one click at the user's mark
        except ValueError: spot = None
        spot_error = spot['width_px']/mark['width']-1 if spot and spot['width_px'] else None
        rows.append(dict(kind='width', gt=mark['width'], spot_error=spot_error, pred=None if r is None else r[0], error=method, reported_error=reported,
                         tube_error=tube_error, tube_none=bool(matched_tube and not matched_tube['width_px']),
                         tip_x=mark['mid'][0], tip_y=mark['mid'][1]))
    seconds = time.time()-started
    rgb = np.asarray(Image.open(image['base']).convert('RGB'))[:bottom]
    return dict(image=image, ump=ump, gray_shape=gray.shape, rows=rows, stroke_rows=stroke_rows, strokes=strokes, complex=complex_count, traces=traces, gt=gt, marks=marks, P=ridge['P'],
                rgb=rgb, seconds=seconds, trace_seconds=time.time()-t0)


def stroke_overlay(rgb, gt, strokes, out):
    canvas = rgb.copy()
    for tube in gt: cv2.polylines(canvas, [np.rint(tube['path']).astype(np.int32)], False, (255, 230, 0), 2)
    for hand, path in strokes:
        cv2.polylines(canvas, [np.rint(hand).astype(np.int32)], False, (0, 200, 255), 1)
        cv2.polylines(canvas, [np.rint(path).astype(np.int32)], False, (255, 0, 255), 1)
    Image.fromarray(canvas).save(out)


def heatmap(rgb, P, out):
    hot = cv2.applyColorMap((np.clip(P, 0, 1)*255).astype(np.uint8), cv2.COLORMAP_INFERNO)[..., ::-1]
    Image.fromarray(np.hstack([rgb, hot])).save(out)


def tube_summary(rows):
    """Metrics of one set of length rows (a bin x waypoints cell)."""
    d = np.array([r['sym_dist'] for r in rows if r['sym_dist'] is not None], float)
    length = stats([r['error'] for r in rows])
    return dict(n=len(rows), sym_median=float(np.median(d)) if len(d) else np.nan, sym_p90=float(np.percentile(d, 90)) if len(d) else np.nan,
                sym_mean=float(d.mean()) if len(d) else np.nan, length_median_abs=length['median_abs'], length_p90_abs=length['p90_abs'],
                match_rate=float(np.mean([r['matched'] for r in rows])) if rows else np.nan)


def stroke_report(results, cells):
    """(markdown lines, verdicts, summary) of the stroke rows next to the click cells. Gates: per bin, stroke median sym dist <= and
    match rate >= the click result at 2 waypoints (same run, same maps); overall match rate >= .95."""
    rows = [r for res in results for r in res['stroke_rows']]
    summary, verdicts = {}, []
    lines = ['## Stroke trace (simulated hand drag)', '',
             f'Per GT tube: the GT path with smooth lateral wander (std {STROKE_AMP} x tube width, correlation ~ one width), each end trimmed or extended by '
             f'U(-{STROKE_END_PX:g}, {STROKE_END_PX:g}) px along the tube and N(0, 1.5) px sideways, sampled every {STROKE_STEP_PX[0]:g}-{STROKE_STEP_PX[1]:g} px with 1 px jitter; '
             'then traced with `trace_stroke`. Tube width for the simulation = median profile width along the GT path. Click columns come from the same run and maps.', '',
             '| bin | tubes | stroke sym median | sym p90 | length median abs err | match rate | click0 sym median | click0 match | click2 sym median | click2 match |', '|---|---|---|---|---|---|---|---|---|---|']
    for b in (*BINS, 'all'):
        s = tube_summary([r for r in rows if b == 'all' or r['bin'] == b])
        summary[b] = s
        c0, c2 = (cells.get(f'{b}|{k}') for k in (0, 2))
        lines.append(f"| {b} | {s['n']} | {s['sym_median']:.2f} | {s['sym_p90']:.2f} | {s['length_median_abs']:.3f} | {s['match_rate']:.3f} | "
                     + ' | '.join(f"{c['sym_median']:.2f} | {c['match_rate']:.3f}" if c else '- | -' for c in (c0, c2)) + ' |')
        if b != 'all' and c2 and s['n']:
            verdicts.append(f"{b}: {'PASS' if s['sym_median'] <= c2['sym_median'] else 'FAIL'}  stroke median sym dist {s['sym_median']:.2f} (click 2 wp {c2['sym_median']:.2f})")
            verdicts.append(f"{b}: {'PASS' if s['match_rate'] >= c2['match_rate'] else 'FAIL'}  stroke match rate {s['match_rate']:.3f} (click 2 wp {c2['match_rate']:.3f})")
    if summary['all']['n']:
        verdicts.append(f"all: {'PASS' if summary['all']['match_rate'] >= .95 else 'FAIL'}  stroke match rate {summary['all']['match_rate']:.3f} (target >= 0.95)")
    shifts = np.array([r['end_shift'] for r in rows if r['end_shift']], float)
    if len(shifts):
        rel = shifts/np.array([r['width'] for r in rows if r['end_shift']])[:, None]
        before, after = np.array([r['tip_before'] for r in rows], float), np.array([r['tip_after'] for r in rows if r['tip_after']], float)
        summary['end_shift'] = e = dict(median=float(np.median(shifts)), max=float(shifts.max()), median_per_width=float(np.median(rel)), max_per_width=float(rel.max()),
            tip_error_stroke_median=float(np.median(before)), tip_error_trace_median=float(np.median(after)), tip_error_trace_max=float(after.max()))
        lines += ['', f"End movement (trace end vs stroke end, {shifts.size} ends): median {e['median']:.1f} px ({e['median_per_width']:.2f} widths), max {e['max']:.1f} px ({e['max_per_width']:.2f} widths).",
                  f"Distance to the nearest GT tip: stroke ends median {e['tip_error_stroke_median']:.1f} px, traced ends median {e['tip_error_trace_median']:.1f} px (max {e['tip_error_trace_max']:.1f}).",
                  f"Failed traces (ValueError): {sum(r['pred'] is None for r in rows)}."]
    lines += ['', '### Gates', '', *[f'- {v}' for v in verdicts], '']
    return lines, verdicts, summary


GATES = {0: (7, 20, .05, .85), 2: (4, 9, .03, .95)}   # D8: median sym, p90 sym, length median |err|, match rate (>=1kx)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--folders', nargs='+', default=['CNT/261103', 'CNT/261105'])
    parser.add_argument('--min-mag', type=float, default=0)
    parser.add_argument('--images', nargs='*', default=[])
    parser.add_argument('--out', default=None, help='default validation/cnt-eval, or validation/cnt-stroke with --stroke')
    parser.add_argument('--waypoints', type=int, nargs='+', default=None, help='interior clicks per tube (simulated Shift-click); one run per value (default 0; 0 2 with --stroke)')
    parser.add_argument('--stroke', action='store_true', help='also trace a simulated hand drag along every GT tube with trace_stroke')
    parser.add_argument('--stroke-amp', type=float, default=STROKE_AMP, help='lateral wander std of the simulated drag, x tube width')
    parser.add_argument('--seed', type=int, default=0, help='random seed of the simulated drags')
    parser.add_argument('--model', choices=['auto', 'none', 'oof'], default='auto',
                        help='none: band filter only; auto: the deployed model (optimistic on training images); oof: out-of-fold maps from --oof-dir')
    parser.add_argument('--folds', default=None, help='folds.json (stem -> fold); written into per_tube.csv')
    parser.add_argument('--oof-dir', default='validation/cnt-learn/oof')
    parser.add_argument('--learned-weight', type=float, default=None, help='override cnt_detect.TRACK_LEARNED')
    parser.add_argument('--turn', type=float, default=None, help='override cnt_detect.TRACK_TURN')
    parser.add_argument('--width', action='store_true', help='also score width (reads X(3).tif)')
    parser.add_argument('--no-overlays', action='store_true')
    args = parser.parse_args()
    if args.model == 'oof' and not args.folds: parser.error('--model oof needs --folds')
    if args.learned_weight is not None: cnt_detect.TRACK_LEARNED = args.learned_weight
    if args.turn is not None: cnt_detect.TRACK_TURN = args.turn
    folds = json.loads(Path(args.folds).read_text(encoding='utf-8')) if args.folds else {}
    out = Path(args.out or ('validation/cnt-stroke' if args.stroke else 'validation/cnt-eval')); out.mkdir(parents=True, exist_ok=True)
    images, skipped = discover(args.folders, args.min_mag, set(args.images))
    waypoints = tuple(args.waypoints or ([0, 2] if args.stroke else [0]))
    stroke = dict(seed=args.seed, amp=args.stroke_amp) if args.stroke else None
    color = (255, 0, 255) if args.model == 'none' else (0, 230, 255)
    results = []
    for image in images:
        stem = image['base'].stem
        result = evaluate(image, waypoints, args.model, args.oof_dir, folds.get(stem), args.width, stroke)
        if not args.no_overlays:
            if stroke: stroke_overlay(result['rgb'], result['gt'], result['strokes'], out/f'{stem}_stroke.png')
            for k in waypoints: overlay(result['rgb'], result['gt'], result['marks'], result['traces'][k], out/f'{stem}_w{k}.png', color)
            if result['P'] is not None: heatmap(result['rgb'], result['P'], out/f'{stem}_P.png')
        results.append(result)
        print(f"{image['base'].name}: {sum(r['kind'] == 'length' for r in result['rows'])//len(waypoints)} certain GT, {result['seconds']:.1f}s", flush=True)
    lengths = [r for res in results for r in res['rows'] if r['kind'] == 'length']
    widths = [r for res in results for r in res['rows'] if r['kind'] == 'width']
    cells = {}
    for k in waypoints:
        for b in (*BINS, 'all'):
            cells[f'{b}|{k}'] = tube_summary([r for r in lengths if r['waypoints'] == k and (b == 'all' or r['bin'] == b)])
    verdicts = []
    for k in waypoints:
        c = cells[f'>=1kx|{k}']
        if k not in GATES or not c['n']: continue
        for name, value, op, limit in (('median sym dist', c['sym_median'], '<=', GATES[k][0]), ('p90 sym dist', c['sym_p90'], '<=', GATES[k][1]),
                                        ('length median |err|', c['length_median_abs'], '<=', GATES[k][2]), ('match rate', c['match_rate'], '>=', GATES[k][3])):
            ok = value >= limit if op == '>=' else value <= limit
            verdicts.append(f">=1kx, {k} waypoints: {'PASS' if ok else 'FAIL'}  {name} {value:.3f} (target {op} {limit})")
    with open(out/'per_tube.csv', 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['image', 'bin', 'model', 'waypoints', 'fold', 'kind', 'x', 'y', 'gt', 'pred', 'relative_error', 'sym_dist', 'trace_matches_gt',
                         'reported_width_error', 'tube_width_error'])
        for res in results:
            fold = folds.get(res['image']['base'].stem)
            for r in res['rows']:
                writer.writerow([res['image']['base'].name, mag_bin(res['image']['mag']), args.model, r.get('waypoints', ''), '' if fold is None else fold, r['kind'],
                                 round(r['tip_x'], 1), round(r['tip_y'], 1), round(r['gt'], 2),
                                 '' if r['pred'] is None else round(r['pred'], 2), '' if r['error'] is None else round(r['error'], 4),
                                 '' if r.get('sym_dist') is None else round(r['sym_dist'], 3), r.get('matched', ''),
                                 '' if r.get('reported_error') is None else round(r['reported_error'], 4),
                                 '' if r.get('tube_error') is None else round(r['tube_error'], 4)])
    fmt = lambda s: f"n={s['n']}, median |e| {s['median_abs']:.3f}, p90 |e| {s['p90_abs']:.3f}, bias {s['bias']:+.3f}"
    constants = ', '.join(f'{k}={getattr(cnt_detect, k)}' for k in dir(cnt_detect) if k.isupper() and k != 'TRACK_DIRS')
    note = {'none': 'Baseline: the band filter only (P = None).', 'auto': 'Deployed model, which has seen all 42 images: optimistic, not a held-out result.',
            'oof': f'Out-of-fold maps ({args.oof_dir}): each image is scored with the model that did not train on it.'}[args.model]
    lines = ['# CNT trace evaluation', '', f'Run {datetime.now():%Y-%m-%d %H:%M}. cnt_detect VERSION {cnt_detect.VERSION}. Model mode `{args.model}`. {note}', '',
             f'Parameters: {constants}', '', f'Images: {len(results)} (min magnification {args.min_mag:g}x). Scale: 279 um / 1024 px at 1kx. '
             'GT lengths: simple (2-tip) polylines of at least 60 px away from the edges; complex GT is counted but excluded. '
             f'Traces are seeded from the two GT tips (two clicks) plus {", ".join(map(str, waypoints))} interior GT waypoint(s).', '',
             '## Mean symmetric distance, length error and match rate', '',
             'sym = 0.5*(mean NN dist trace->GT + GT->trace) on 1-px paths, px. match = 70% of both directions within max(6, .75*band) px.', '',
             '| bin | waypoints | tubes | sym median | sym p90 | sym mean | length median abs err | length p90 abs err | match rate |', '|---|---|---|---|---|---|---|---|---|']
    for b in (*BINS, 'all'):
        for k in waypoints:
            c = cells[f'{b}|{k}']
            lines.append(f"| {b} | {k} | {c['n']} | {c['sym_median']:.2f} | {c['sym_p90']:.2f} | {c['sym_mean']:.2f} | {c['length_median_abs']:.3f} | {c['length_p90_abs']:.3f} | {c['match_rate']:.3f} |")
    lines += ['', '## D8 gates (>=1kx)', '', *[f'- {v}' for v in verdicts], '']
    stroke_summary = None
    if stroke:
        stroke_lines, stroke_verdicts, stroke_summary = stroke_report(results, cells)
        lines += stroke_lines
        verdicts += stroke_verdicts
        with open(out/'stroke_tubes.csv', 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['image', 'bin', 'tube_width', 'gt_length', 'stroke_length', 'pred_length', 'relative_error', 'sym_dist', 'trace_matches_gt', 'start_shift', 'end_shift',
                             'stroke_start_to_tip', 'stroke_end_to_tip', 'trace_start_to_tip', 'trace_end_to_tip'])
            for res in results:
                for r in res['stroke_rows']:
                    shift, after = r['end_shift'] or ['', ''], r['tip_after'] or ['', '']
                    writer.writerow([res['image']['base'].name, r['bin'], round(r['width'], 1), round(r['gt'], 1), round(r['stroke_length'], 1), '' if r['pred'] is None else round(r['pred'], 1),
                                     '' if r['error'] is None else round(r['error'], 4), '' if r['sym_dist'] is None else round(r['sym_dist'], 3), r['matched'],
                                     *[v if v == '' else round(v, 2) for v in shift], *[round(v, 2) for v in r['tip_before']], *[v if v == '' else round(v, 2) for v in after]])
    (out/'summary.json').write_text(json.dumps(dict(model=args.model, learned=cnt_detect.TRACK_LEARNED, turn=cnt_detect.TRACK_TURN,
                                                    waypoints=list(waypoints), images=len(results), cells=cells,
                                                    stroke=None if stroke_summary is None else dict(amp=args.stroke_amp, seed=args.seed, cells=stroke_summary)), indent=1), encoding='utf-8')
    if args.width:
        values = [stats([r['error'] for r in widths]), stats([r.get('reported_error') for r in widths]), stats([r.get('tube_error') for r in widths]),
                  stats([r.get('spot_error') for r in widths])]
        lines += ['## Width (not part of the learned-model comparison)', '', f'- method at GT marks: {fmt(values[0])}', f'- reported by traces near marks: {fmt(values[1])}',
                  f'- traced tube D vs user D mark: {fmt(values[2])}', f'- Width-only click at each mark: {fmt(values[3])}', '']
    lines += ['## Per image', '', f'Waypoints {waypoints[0]}.', '', '| image | mag | um/px | certain GT | complex GT | matched | sym median | median length err | seconds |', '|---|---|---|---|---|---|---|---|---|']
    for res in results:
        l = [r for r in res['rows'] if r['kind'] == 'length' and r['waypoints'] == waypoints[0]]
        ls = stats([r['error'] for r in l])
        sd = [r['sym_dist'] for r in l if r['sym_dist'] is not None]
        lines.append(f"| {res['image']['base'].name} | {res['image']['mag']:g} | {res['ump']:.4f} | {len(l)} | {res['complex']} | {int(sum(r['matched'] for r in l))} | "
                     f"{np.median(sd) if sd else float('nan'):.2f} | {ls['median_abs']:.3f} | {res['seconds']:.1f} |")
    lines += ['', '## Skipped', '', *[f'- {s}' for s in skipped]]
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('\n'.join(verdicts)); print(f'wrote {out/"report.md"}')


if __name__ == '__main__':
    main()
