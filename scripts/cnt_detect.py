"""Carbon-nanotube tube measurement: oriented trace between clicks, centerline, length, width.

Pure numpy/scipy/skimage/cv2, no application state. Paths are (N, 2) float
arrays with columns x, y in ROI pixel coordinates, the same convention as
``annotations[id]['manual_measurements']``. See docs/cnt-design.md.
"""
import logging
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage as ndi
from scipy.interpolate import splev, splprep
from scipy.spatial import cKDTree
from scipy.signal import savgol_filter
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from skimage.filters import sato

from lab_geometry import geometry

log = logging.getLogger(__name__)
VERSION = 3
MODEL_FILE = 'checkpoints/openvino/cnt_centerline.xml'   # learned centerline map; absent file = VERSION 2 behaviour
TRACK_LEARNED = 0.6                  # 0.6: no OOF regression vs band-only in any mag bin at 0-2 waypoints; weight of the learned map P in the tracker response (0 = band filter only)
TUBE_WIDTH_UM = (1.5, 16.0)          # expected tube widths, calibrated
TUBE_WIDTH_PX = (8.0, 68.0)          # uncalibrated ('px' unit) fallback
SIGMA_COUNT = 5
SIGMA_PER_RADIUS = 1/1.7             # sato sigma ~ radius/1.7
SIGMA_CLAMP = (1.5, 20.0)
BACKGROUND_SIGMA = 40.0              # flat-field: f - gaussian(f, 40)
PRE_SMOOTH_SIGMA = 1.5
TRACE_EPS, TRACE_CLIP = 0.05, 2.0
TRACE_MAX_POINTS = 20
SMOOTH_PER_SIGMA = 10.0              # centerline smoothing window, x median ridge sigma
DECIMATE_STEP = 3                    # keep every 3rd vertex (+ last) of the 1-px path
WIDTH_STATIONS = (0.20, 0.35, 0.50, 0.65, 0.80)   # coarse stations that estimate the tube width W
SECTION_TRIM = .15                   # outer fraction of the path at each end that is never used for D
SECTION_SPACING = 1/3                # clean-section scan step, x W
SECTION_QMIN = .40                   # minimum quality of a section reported as clean
SECTION_RUN = 2                      # stations on each side of the best one that may join the run
SECTION_CONSISTENCY = .15            # neighbouring stations must agree within 15%
WIDTH_LEVEL = 0.25
WIDTH_HALF0_UM, WIDTH_HALF0_PX = 8.0, 30.0
WIDTH_HALF_CLAMP = (10.0, 120.0)
WIDTH_REFINE = 2
WIDTH_STEP = 0.25                    # profile sample spacing, px
WIDTH_OFFSETS = (-3, -2, -1, 0, 1, 2, 3)   # parallel profiles along tangent, px
WIDTH_SMOOTH_PX = 1.5
WIDTH_MIN_CONTRAST = 4.0             # gray levels, peak - background
BAND_PER_SIGMA = 3.5                 # mask band when no width: 3.5 x median sigma
TRACK_SCALES = (0.6, 1.0, 1.6)       # oriented filter widths, x estimated tube width
TRACK_KERNEL_LENGTH = 1.5            # filter length along the tube, x filter width
TRACK_CELLS_PER_WIDTH = 5.0          # lattice cells across the narrowest filter
TRACK_MAX_CELLS = 12000              # lattice size cap per segment (speed)
TRACK_MARGIN = 1.0                   # search box margin, x click distance (+3 widths)
TRACK_PERCENTILE = 97                # response normalisation
TRACK_GAMMA = 2.0                    # cost = 1/(eps+response^gamma): faint clutter costs more
TRACK_TURN = 0.5                     # cost of one 22.5 deg bend, x width (px of ideal tube)
TRACK_SMOOTH = 1.5                   # Savitzky-Golay window of a width-only spot path, x width
TRACK_CURVE = 0.15                   # traced line = smoothing spline within ~0.15 widths of the tracked path: a natural curve, no texture wiggle
                                     # (70 OOF tubes vs Savitzky-Golay 1.5 W: turning 227 -> 55 deg/100 px, sym 3.18 -> 2.92 px, length 2-3% shorter)
TRACK_RAY = 3.0                      # end-heading probe length, x width
TRACK_OUTSIDE = 1e3                  # cost of a lattice cell outside a stroke corridor (a normal background cell costs ~20)
STROKE_MAX_POINTS = 2000
STROKE_CORRIDOR = 0.5                # corridor radius around the stroke, x tube width
STROKE_CORRIDOR_MIN = 10.0           # px
STROKE_SPACING = 2.0                 # a waypoint every 2 widths of stroke
STROKE_SNAP = 0.3                    # sideways snap of a waypoint / stroke end onto the ridge, x width
STROKE_TIP = 1.0                     # an end drawn outside the tube moves along it at most this far to reach the tip, x width
STROKE_GUIDE_WINDOW = 15             # Savitzky-Golay window of the 1-px stroke, px
STROKE_PULL = 0.2                    # the drawn line moves toward the tracked tube centre by at most this, x width: the user's drag is the answer
STROKE_PULL_SIGMA = 1.0              # smoothing of that pull along the line, x width
STROKE_CURVE = 0.05                  # final light spline, x width (removes hand jitter only)
BOX_MIN_PX = (2., 6.)                # a measuring box needs sides of at least (short, long) px
TRACK_DIRS = np.array([(2, 0), (2, 1), (1, 1), (1, 2), (0, 2), (-1, 2), (-1, 1), (-2, 1),
                       (-2, 0), (-2, -1), (-1, -1), (-1, -2), (0, -2), (1, -2), (1, -1), (2, -1)])  # ~22.5 deg apart


def sigmas_for(um_per_pixel, calibrated):
    if calibrated:
        rmin, rmax = (w/2/um_per_pixel for w in TUBE_WIDTH_UM)
    else:
        rmin, rmax = (w/2 for w in TUBE_WIDTH_PX)
    low, high = rmin*SIGMA_PER_RADIUS, rmax*SIGMA_PER_RADIUS
    if low > SIGMA_CLAMP[1]:
        return [SIGMA_CLAMP[1]]  # shortcut: very high magnification gets one poor-fit scale
    low = max(SIGMA_CLAMP[0], low)
    return list(np.geomspace(low, max(low, min(SIGMA_CLAMP[1], high)), SIGMA_COUNT))


def ridge_response(gray, um_per_pixel, calibrated):
    f = gray.astype(np.float32)/255
    f = f-ndi.gaussian_filter(f, BACKGROUND_SIGMA)
    f = ndi.gaussian_filter(f, PRE_SMOOTH_SIGMA)
    sigmas = sigmas_for(um_per_pixel, calibrated)
    stack = np.stack([sato(f, sigmas=[s], black_ridges=False) for s in sigmas]).astype(np.float32)
    R = stack.max(0)
    sigma = np.asarray(sigmas, np.float32)[stack.argmax(0)]
    return dict(R=R, sigma=sigma, sigmas=sigmas, um_per_pixel=float(um_per_pixel), calibrated=bool(calibrated))


def normalise_gray(gray):
    """p1/p99 stretch to float32 [0, 1]: the one normalisation shared by training and inference."""
    g = np.asarray(gray, np.float32)
    lo, hi = np.percentile(g, (1, 99))
    return np.clip((g-lo)/max(float(hi-lo), 1e-6), 0, 1).astype(np.float32)


_models, _warned = {}, set()


def centerline_map(gray, model_path=None):
    """Learned 'a user would trace a centerline here' map, float32 (H, W) in [0, 1]; None when there is no model."""
    if model_path is None:
        from app_paths import ASSET_ROOT
        model_path = ASSET_ROOT/MODEL_FILE
    key = str(model_path)
    try:
        if key not in _models:
            if not Path(model_path).is_file(): raise FileNotFoundError(key)
            import openvino as ov
            _models[key] = ov.Core().compile_model(key, 'CPU')
        x = normalise_gray(gray)
        height, wide = x.shape
        x = np.pad(x, ((0, -height % 16), (0, -wide % 16)), mode='reflect')   # U-Net depth 4 needs multiples of 16
        return np.clip(np.asarray(_models[key](x[None, None])[0])[0, 0, :height, :wide], 0, 1).astype(np.float32)
    except Exception as e:
        if key not in _warned:
            _warned.add(key); log.warning('CNT centerline model unavailable (%s: %s); using the band filter only.', type(e).__name__, e)
        return None


def resample(path, step=1.0):
    path = np.asarray(path, float)
    arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
    if arc[-1] <= 0:
        raise ValueError('Cannot trace a centerline in this object.')
    s = np.arange(0, arc[-1], step)
    if arc[-1]-s[-1] > 1e-6: s = np.r_[s, arc[-1]]
    return np.column_stack([np.interp(s, arc, path[:, k]) for k in (0, 1)])


def smooth_path(p, window):
    if len(p) <= window: return p
    # Savitzky-Golay (quadratic) removes texture wiggle but keeps real bends, unlike a box average
    out = np.column_stack([savgol_filter(p[:, k], window, 2, mode='interp') for k in (0, 1)])
    out[0], out[-1] = p[0], p[-1]
    return out


def curve_path(p, tolerance):
    """1-px path p as a smooth curve: cubic smoothing spline that stays within about `tolerance` px (rms) of p; ends fixed."""
    if len(p) < 12: return p
    q = np.vstack((p[:-1:3], p[-1]))
    weight = np.ones(len(q)); weight[[0, -1]] = 1e3
    tck, _ = splprep(q.T, w=weight, s=len(q)*tolerance**2, k=3)
    out = resample(np.column_stack(splev(np.linspace(0, 1, len(p)), tck)))
    out[0], out[-1] = p[0], p[-1]
    return out


def profile_width(gray, center, tangent, half):
    gray = np.asarray(gray, float)
    normal = np.array([-tangent[1], tangent[0]])
    t = np.arange(-half, half+WIDTH_STEP, WIDTH_STEP)
    profile = np.mean([ndi.map_coordinates(gray,
        [center[1]+t*normal[1]+o*tangent[1], center[0]+t*normal[0]+o*tangent[0]], order=1, mode='nearest')
        for o in WIDTH_OFFSETS], axis=0)
    profile = ndi.gaussian_filter1d(profile, WIDTH_SMOOTH_PX/WIDTH_STEP)
    q = max(4, len(t)//8)
    bg = float(np.median(np.r_[profile[:q], profile[-q:]]))
    lo_core, hi_core = len(t)//4, 3*len(t)//4
    top = lo_core+int(np.argmax(profile[lo_core:hi_core]))
    peak = float(profile[top])
    if peak-bg < WIDTH_MIN_CONTRAST: return None
    above = profile >= bg+WIDTH_LEVEL*(peak-bg)
    runs, _ = ndi.label(above)
    run = np.flatnonzero(runs == runs[top])
    inner = np.flatnonzero(above & (np.abs(t) <= .8*half))
    if not len(inner): return None
    lo, hi = min(run[0], inner[0]), max(run[-1], inner[-1])
    return float(t[hi]-t[lo]), center+t[lo]*normal, center+t[hi]*normal


def width_at(gray, center, tangent, um_per_pixel, calibrated):
    gray = np.asarray(gray, float)
    half = WIDTH_HALF0_UM/um_per_pixel if calibrated else WIDTH_HALF0_PX
    result = profile_width(gray, center, tangent, float(np.clip(half, *WIDTH_HALF_CLAMP)))
    for _ in range(WIDTH_REFINE):
        if result is None: break
        result = profile_width(gray, center, tangent, float(np.clip(.75*result[0]+6, *WIDTH_HALF_CLAMP)))
    return result


def station_terms(gray, center, tangent, r, path, arc, s):
    """Quality terms in [0, 1] of one width station: edges, symmetry, flat dark surroundings, straightness."""
    w = r[0]
    mid = (r[1]+r[2])/2
    normal = np.array([-tangent[1], tangent[0]])
    if (r[2]-r[1])@normal < 0: normal = -normal
    half, step = 1.5*w+3, .5
    u, v = np.arange(-w, w+1., 1.), np.arange(-half, half+step, step)
    uu, vv = np.meshgrid(u, v, indexing='ij')
    patch = ndi.map_coordinates(gray, [mid[1]+uu*tangent[1]+vv*normal[1], mid[0]+uu*tangent[0]+vv*normal[0]], order=1, mode='nearest')
    profile = ndi.gaussian_filter1d(patch[np.abs(u) <= 3].mean(0), WIDTH_SMOOTH_PX/step)
    inner = np.abs(v) < w/2-2
    gap = max(3., .2*w)  # skip the edge halo
    left, right = (v >= -w/2-w) & (v <= -w/2-gap), (v <= w/2+w) & (v >= w/2+gap)
    if not inner.any() or not left.any() or not right.any(): return None
    bg_l, bg_r = float(np.median(patch[:, left])), float(np.median(patch[:, right]))
    contrast = float(profile[inner].max()-(bg_l+bg_r)/2)
    if contrast < WIDTH_MIN_CONTRAST: return None
    slope = np.abs(np.gradient(profile, step))/contrast
    edge = min(slope[np.abs(v+w/2) <= 3].max(), slope[np.abs(v-w/2) <= 3].max())
    clutter = max((np.percentile(patch[:, side], 90)-np.median(patch[:, side]))/contrast for side in (left, right))
    along = patch[:, inner].mean(1).std()/contrast  # a fibre crossing the tube body makes the interior vary along it
    behind, ahead = (np.array([np.interp(np.clip(s+d, 0, arc[-1]), arc, path[:, k]) for k in (0, 1)]) for d in (-w, w))
    bend = np.degrees(np.arccos(np.clip(_unit(center-behind)@_unit(ahead-center), -1, 1)))
    ramp = lambda x, good, bad: float(np.clip((bad-x)/(bad-good), 0, 1))
    return [ramp(edge, .10, .03), ramp(abs(bg_l-bg_r)/contrast, .05, .30),
            ramp(abs(float((mid-center)@normal))/w, .05, .25), ramp(clutter, .15, .6), ramp(along, .08, .30), ramp(bend, 6, 25)]


def _unit(x):
    return x/max(float(np.linalg.norm(x)), 1e-9)


def tube_width(gray, p, um_per_pixel, calibrated, near=None, force=False):
    """D on a clean section: scan stations every ~W/3 (outer 15% skipped), score each (edges, symmetry, flat dark
    surroundings, no crossing fibre, straightness, width agreeing with its neighbours) and report the median width of
    the best contiguous run, with the mark drawn at its best station. None when no section is clean (unless force)."""
    none = dict(width_px=None, width_line=[], width_stations=[], width_station=None, prelim_px=None)
    if len(p) < 2: return none
    gray = np.asarray(gray, float)
    arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    point = lambda s: np.array([np.interp(np.clip(s, 0, arc[-1]), arc, p[:, k]) for k in (0, 1)])
    tangent = lambda s: _unit(point(s+5)-point(s-5))
    coarse = [width_at(gray, point(f*arc[-1]), tangent(f*arc[-1]), um_per_pixel, calibrated) for f in WIDTH_STATIONS]
    coarse = [r[0] for r in coarse if r is not None]
    if not coarse: return none
    prelim = float(np.median(coarse))
    lo, hi = SECTION_TRIM*arc[-1], (1-SECTION_TRIM)*arc[-1]
    positions = np.arange(lo, hi+1e-6, max(3., prelim*SECTION_SPACING)) if hi > lo else np.array([arc[-1]/2])
    stations = []
    for s in positions:
        r = width_at(gray, point(s), tangent(s), um_per_pixel, calibrated)
        terms = None if r is None else station_terms(gray, point(s), tangent(s), r, p, arc, s)
        stations.append((s, r, terms))
    widths = [None if r is None or t is None else r[0] for _, r, t in stations]
    quality = []
    for i, (s, r, terms) in enumerate(stations):
        if widths[i] is None: quality.append(0.); continue
        around = [abs(widths[j]-widths[i])/widths[i] for j in (i-1, i+1) if 0 <= j < len(widths) and widths[j] is not None]
        t = terms+[float(np.clip((SECTION_CONSISTENCY*1.3-max(around, default=0))/(SECTION_CONSISTENCY*.8), 0, 1))]
        quality.append(float(np.mean(t))*(.35+.65*min(1., 2*min(t))))  # a term at zero caps the quality below SECTION_QMIN
    q = np.asarray(quality)
    smooth = np.array([min(q[i], q[max(i-1, 0):i+2].mean()) for i in range(len(q))])  # a clean section is extended, not one lucky station
    score = smooth.copy()
    if near is not None:
        score -= .15*np.abs(positions-near)/(3*prelim)  # D-only: prefer the part close to the click
    best = int(np.argmax(score))
    if smooth[best] < SECTION_QMIN and not force or widths[best] is None:
        return dict(none, prelim_px=round(prelim, 2))
    run = [best]
    for direction in (-1, 1):
        j = best+direction
        while 0 <= j < len(q) and abs(j-best) <= SECTION_RUN and widths[j] is not None and q[j] >= .8*SECTION_QMIN                 and abs(widths[j]-widths[best])/widths[best] <= SECTION_CONSISTENCY:
            run.append(j); j += direction
    run.sort()
    width = float(np.median([widths[j] for j in run]))
    pick = min(run, key=lambda j: (abs(widths[j]-width)/width > .05, -q[j], abs(widths[j]-width)))
    r = stations[pick][1]
    mid, across = (r[1]+r[2])/2, _unit(r[2]-r[1])
    return dict(width_px=round(width, 2), width_line=[(mid-across*width/2).tolist(), (mid+across*width/2).tolist()],
                width_stations=[round(widths[j], 2) for j in run], prelim_px=round(prelim, 2),
                width_station=dict(s=round(float(stations[pick][0]), 1), fraction=round(float(stations[pick][0]/arc[-1]), 3),
                                   quality=round(float(smooth[best]), 3), clean=bool(smooth[best] >= SECTION_QMIN), stations=len(run)))


def tube_mask(shape, path, band_px):
    mask = np.zeros(shape, np.uint8)
    cv2.polylines(mask, [np.rint(path).astype(np.int32)], False, 1, max(3, int(round(band_px))))
    return mask.astype(bool)


def finish_candidate(gray, ridge, raw_path, source, window=None, near_point=None, force=False, curve=None):
    p = resample(raw_path)
    sigma = ridge['sigma']
    height, width = sigma.shape
    at = lambda q: float(np.median(sigma[np.clip(np.rint(q[:, 1]).astype(int), 0, height-1), np.clip(np.rint(q[:, 0]).astype(int), 0, width-1)]))
    window = max(3, int(round(window or SMOOTH_PER_SIGMA*at(p)))) | 1
    p = smooth_path(p, window) if curve is None else curve_path(p, curve) if curve else p   # curve=0: the path as given
    p = np.column_stack((np.clip(p[:, 0], 0, width-1), np.clip(p[:, 1], 0, height-1)))
    near = None
    if near_point is not None:  # arc position of the click on the path
        near = float(np.r_[0., np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))][int(np.argmin(np.linalg.norm(p-near_point, axis=1)))])
    measured = tube_width(gray, p, ridge['um_per_pixel'], ridge['calibrated'], near, force)
    path = p[::DECIMATE_STEP]
    if (len(p)-1) % DECIMATE_STEP: path = np.vstack((path, p[-1]))
    length = float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum())  # from the stored path, so UI and CSV agree
    return dict(source=source, path=path, length_px=length, width_px=measured['width_px'],
                width_line=measured['width_line'], width_stations=measured['width_stations'], width_station=measured['width_station'],
                band_px=float(measured['prelim_px'] or BAND_PER_SIGMA*at(p)))  # whole-tube width, not the clean section's


def spot_width(ridge):
    lo, hi = (w/ridge['um_per_pixel'] for w in TUBE_WIDTH_UM) if ridge['calibrated'] else TUBE_WIDTH_PX
    return np.geomspace(max(lo, 6.), max(min(hi, 80.), 7.), 6)


def measure_spot(gray, ridge, point, box=None):
    """D-only: snap the click to the strongest oriented tube response within ~W, take its heading, trace a short
    centerline (+-3W) and measure the clean section nearest the click. The result is flagged clean or not.
    With a box (clean_box; point = its centre) the snap region is the box, tubes wider than its longer side are not
    tried, and D is taken from the part of the centerline inside the box."""
    height, wide = gray.shape
    x, y = float(point[0]), float(point[1])
    if not (0 <= x < wide and 0 <= y < height): raise ValueError('Click inside the image.')
    f = np.asarray(gray, np.float32)
    best = None
    scales = spot_width(ridge)
    if box is not None: scales = [ws for ws in scales if ws <= max(box[2]-box[0], box[3]-box[1])] or scales[:1]
    for ws in scales:
        r = int(2*ws+10)
        x0, y0, x1, y1 = max(int(x)-r, 0), max(int(y)-r, 0), min(int(x)+r+1, wide), min(int(y)+r+1, height)
        if box is not None: x0, y0, x1, y1 = max(int(box[0])-r, 0), max(int(box[1])-r, 0), min(int(box[2])+r+2, wide), min(int(box[3])+r+2, height)
        crop = f[y0:y1, x0:x1]
        yy, xx = np.mgrid[y0:y1, x0:x1]
        near = (yy-y)**2+(xx-x)**2 <= max(ws, 8.)**2  # snap radius ~ W
        if box is not None: near = (xx >= box[0]) & (xx <= box[2]) & (yy >= box[1]) & (yy <= box[3])
        for k, kernel in enumerate(oriented_kernels(ws)):
            response = cv2.filter2D(crop, -1, kernel, borderType=cv2.BORDER_REFLECT)
            response = np.where(near, response, -np.inf)
            i = int(np.argmax(response))
            if best is None or response.flat[i] > best[0]:
                best = (float(response.flat[i]), ws, k, np.array([xx.flat[i], yy.flat[i]], float))
    _, ws, k, c = best
    heading = np.array([np.cos(np.deg2rad(22.5*k)), np.sin(np.deg2rad(22.5*k))])
    r = width_at(gray, c, heading, ridge['um_per_pixel'], ridge['calibrated'])
    if r is None: raise ValueError('No tube found in this box. Draw the box on the tube.' if box is not None else 'No tube found at this spot. Click on the tube.')
    w, c = float(r[0]), (r[1]+r[2])/2
    ends = []
    for sign in (-1, 1):
        e = np.clip(c+sign*3*w*heading, 0, [wide-1, height-1])
        rr = width_at(gray, e, heading, ridge['um_per_pixel'], ridge['calibrated'])
        ends.append((rr[1]+rr[2])/2 if rr is not None else e)  # recentre each end on the tube
    if np.linalg.norm(ends[1]-ends[0]) < 2*w: raise ValueError('The tube is too close to the image edge here.')
    piece, _ = track_segment(f, ends[0], ends[1], w)
    candidate = finish_candidate(gray, ridge, piece, 'spot', TRACK_SMOOTH*w, near_point=c, force=True)
    inside = None if box is None else box_piece(candidate['path'], box)
    if inside is not None:
        try: candidate.update(box_width(gray, ridge, inside, box))
        except ValueError: pass   # keep the clean section measured on the whole spot trace
    return candidate


def clean_box(box, shape):
    """[x0, y0, x1, y1] in any corner order -> float array clipped to the image; ValueError for anything unusable."""
    message = 'Draw a box of at least a few pixels on the tube, inside the image.'
    try:
        b = np.asarray(box, float)
    except (TypeError, ValueError):
        raise ValueError(message)
    if b.shape != (4,) or not np.isfinite(b).all(): raise ValueError(message)
    height, wide = shape
    b = np.array([min(b[0], b[2]), min(b[1], b[3]), max(b[0], b[2]), max(b[1], b[3])])
    b = np.clip(b, 0, [wide-1, height-1, wide-1, height-1])
    sides = np.sort([b[2]-b[0], b[3]-b[1]])
    if sides[0] < BOX_MIN_PX[0] or sides[1] < BOX_MIN_PX[1]: raise ValueError(message)
    return b


def box_piece(path, box):
    """The longest run of a path (1-px samples) inside the box, or None when it has fewer than 2 samples there."""
    p = resample(path)
    runs, count = ndi.label((p[:, 0] >= box[0]) & (p[:, 0] <= box[2]) & (p[:, 1] >= box[1]) & (p[:, 1] <= box[3]))
    if not count: return None
    best = int(np.argmax(np.bincount(runs.ravel())[1:]))+1
    piece = p[runs == best]
    return piece if len(piece) >= 2 else None


def box_width(gray, ridge, piece, box):
    """D on the part of a centerline inside a box: the same section search as the whole tube, run on the piece, always
    reporting the best section (the user chose the place), the one nearest the box centre preferred."""
    arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(piece, axis=0), axis=1))]
    near = float(arc[int(np.argmin(np.linalg.norm(piece-[(box[0]+box[2])/2, (box[1]+box[3])/2], axis=1)))])
    m = tube_width(gray, piece, ridge['um_per_pixel'], ridge['calibrated'], near, force=True)
    if m['width_px'] is None: raise ValueError('No width could be measured in this box. Move it onto a clearer part of the tube.')
    return dict(width_px=m['width_px'], width_line=m['width_line'], width_stations=m['width_stations'], width_station=m['width_station'])


def oriented_kernels(width):
    """8 zero-mean line filters (0..157.5 deg): +band of `width`, -flanks of width/2, length TRACK_KERNEL_LENGTH*width."""
    length = max(TRACK_KERNEL_LENGTH*width, 2.)
    r = int(np.ceil(max(length/2, width)+1))
    yy, xx = np.mgrid[-r:r+1, -r:r+1].astype(float)
    kernels = []
    for k in range(8):
        a = np.deg2rad(22.5*k)
        u, v = xx*np.cos(a)+yy*np.sin(a), -xx*np.sin(a)+yy*np.cos(a)
        along = np.clip(length/2+.5-np.abs(u), 0, 1)
        band = np.clip(width/2+.5-np.abs(v), 0, 1)*along
        flank = np.clip(width+.5-np.abs(v), 0, 1)*along-band
        kernels.append((band/band.sum()-flank/max(flank.sum(), 1e-9)).astype(np.float32))
    return kernels


def track_segment(f, a, b, width, heading=None, P=None, guide=None, radius=0.):
    """Cheapest path a->b on a (cell, heading) lattice. Cost is low along an oriented band of the tube's
    width (centre, not one bright edge) and every 22.5 deg bend costs extra, so the path goes straight
    through crossings instead of switching strands. P (optional, same shape as f) is the learned centerline map, blended
    into the response. guide (optional, (N, 2) xy) with radius keeps the path within `radius` px of that polyline: the search
    box is then the guide's, since the ends of a bent guide can be close together.
    Returns (path xy, arrival heading index 0..15)."""
    height, wide = f.shape
    if guide is None:
        margin = TRACK_MARGIN*np.linalg.norm(b-a)+3*width
        lo, hi = np.minimum(a, b)-margin, np.maximum(a, b)+margin
    else:
        lo, hi = guide.min(0)-radius-3*width, guide.max(0)+radius+3*width
    x0, y0 = int(max(lo[0], 0)), int(max(lo[1], 0))
    x1, y1 = int(min(hi[0]+1, wide)), int(min(hi[1]+1, height))
    crop = f[y0:y1, x0:x1]
    widths = [width*k for k in TRACK_SCALES]
    s = max(1, int(round(min(widths)/TRACK_CELLS_PER_WIDTH)), int(np.ceil(np.sqrt(crop.size/TRACK_MAX_CELLS))))
    h, w = max(crop.shape[0]//s, 1), max(crop.shape[1]//s, 1)
    small = cv2.resize(crop[:h*s, :w*s], (w, h), interpolation=cv2.INTER_AREA) if s > 1 else crop
    response = None
    for ws in widths:  # max over widths, each normalised: robust to a wrong width estimate
        o = np.stack([cv2.filter2D(small, -1, k, borderType=cv2.BORDER_REFLECT) for k in oriented_kernels(ws/s)])
        o /= max(float(np.percentile(o.max(0), TRACK_PERCENTILE)), 1e-6)
        response = o if response is None else np.maximum(response, o)
    if P is not None:  # the learned map replaces part of the band response, so the sub-cell parabola centres on the blend too
        p = P[y0:y0+h*s, x0:x0+w*s]
        p = cv2.resize(p, (w, h), interpolation=cv2.INTER_AREA) if s > 1 else p
        response = (1-TRACK_LEARNED)*response+TRACK_LEARNED*TRACE_CLIP*p[None]
    cost = 1/(TRACE_EPS+np.clip(response, 0, TRACE_CLIP)**TRACK_GAMMA)
    if guide is not None:
        inside = np.zeros((h, w), np.uint8)   # cell centres sit at (index+.5)*s; polylines takes 1/16 px fixed point
        cv2.polylines(inside, [np.rint(((guide-[x0, y0])/s-.5)*16).astype(np.int32)], False, 1, max(1, int(round(2*radius/s))), cv2.LINE_8, shift=4)
        cost = np.where(inside > 0, cost, TRACK_OUTSIDE)
    cost = np.concatenate([cost, cost])                     # 16 directed headings share 8 orientations
    n = 16*h*w
    K, Y, X = np.meshgrid(np.arange(16), np.arange(h), np.arange(w), indexing='ij')
    src, dst, weight = [], [], []
    for turn in (-1, 0, 1):
        K2 = (K+turn) % 16
        step = TRACK_DIRS[K2]
        X2, Y2 = X+step[..., 0], Y+step[..., 1]
        ok = (X2 >= 0) & (X2 < w) & (Y2 >= 0) & (Y2 < h)
        c = np.linalg.norm(step, axis=-1)*s*.5*(cost[K2, Y, X]+cost[K2, np.clip(Y2, 0, h-1), np.clip(X2, 0, w-1)])
        src.append(((K*h+Y)*w+X)[ok]); dst.append(((K2*h+Y2)*w+X2)[ok]); weight.append((c+abs(turn)*TRACK_TURN*width)[ok])
    cell = lambda p: (int(np.clip((p[1]-y0)//s, 0, h-1)), int(np.clip((p[0]-x0)//s, 0, w-1)))
    (ay, ax), (by, bx) = cell(a), cell(b)
    ks = np.arange(16)
    # source node n enters the start cell at any heading; after a waypoint, leaving at a new heading costs like a bend
    enter = np.zeros(16) if heading is None else np.minimum((ks-heading) % 16, (heading-ks) % 16)*TRACK_TURN*width
    src.append(np.full(16, n)); dst.append((ks*h+ay)*w+ax); weight.append(enter+1e-6)
    graph = csr_matrix((np.concatenate(weight), (np.concatenate(src), np.concatenate(dst))), shape=(n+1, n+1))
    dist, pred = dijkstra(graph, indices=n, return_predecessors=True)
    node = min(((k*h+by)*w+bx for k in ks), key=lambda i: dist[i])  # the lattice is connected, so always reached
    nodes = [node]
    while pred[nodes[-1]] != n: nodes.append(pred[nodes[-1]])
    nodes = np.array(nodes[::-1])
    k, yx = (nodes//(h*w)) % 8, np.column_stack([(nodes//w) % h, nodes % w]).astype(float)
    # sub-cell centre: parabola through the response at -1, 0, +1 cells across the heading
    normal = np.column_stack([np.cos(np.deg2rad(22.5*k)), -np.sin(np.deg2rad(22.5*k))])   # (dy, dx)
    r = [ndi.map_coordinates(response, [k, yx[:, 0]+o*normal[:, 0], yx[:, 1]+o*normal[:, 1]], order=1, mode='nearest') for o in (-1, 0, 1)]
    curvature = np.minimum(r[0]-2*r[1]+r[2], -1e-9)
    yx += np.clip(.5*(r[0]-r[2])/curvature, -1, 1)[:, None]*normal
    xy = yx[:, ::-1]*s+(s-1)/2+[x0, y0]
    return np.vstack([a, xy[1:-1], b]), int(node//(h*w))


def end_heading(R, a, b, width):
    """Direction from click a into the tube: the ray of length TRACK_RAY*width with the strongest ridge."""
    s = np.linspace(width/4, TRACK_RAY*width, 12)
    u = (b-a)/max(np.linalg.norm(b-a), 1e-9)
    angles = np.deg2rad(np.arange(0, 360, 7.5))
    rays = np.column_stack([np.cos(angles), np.sin(angles)])
    pts = a+s[None, :, None]*rays[:, None, :]
    v = ndi.map_coordinates(R, [pts[..., 1], pts[..., 0]], order=1, mode='nearest').mean(1)+.02*float(R.max())*(rays@u)
    return rays[int(np.argmax(v))]


def trace_width(gray, ridge, pts):
    """Tube width for the tracker: median profile width just inside both end clicks (sato scale if none)."""
    guess = 2*float(np.median(ridge['sigma']))/SIGMA_PER_RADIUS
    widths = []
    for end, toward in ((pts[0], pts[1]), (pts[-1], pts[-2])):
        h = end_heading(ridge['R'], end, toward, guess)
        for d in (8, 16, 24, 32):
            r = width_at(gray, end+d*h, h, ridge['um_per_pixel'], ridge['calibrated'])
            if r is not None: widths.append(r[0])
    return float(np.clip(np.median(widths) if widths else guess, 6, 80))


def trace_tube(gray, ridge, points):
    message = f'Trace needs 2 to {TRACE_MAX_POINTS} points inside the image.'
    height, width = ridge['R'].shape
    try:
        pts = np.asarray(points, float)
    except (TypeError, ValueError):
        raise ValueError(message)
    if pts.ndim != 2 or pts.shape[1] != 2 or not 2 <= len(pts) <= TRACE_MAX_POINTS or not np.isfinite(pts).all() \
            or (pts < 0).any() or (pts[:, 0] >= width).any() or (pts[:, 1] >= height).any():
        raise ValueError(message)
    if (np.linalg.norm(np.diff(pts, axis=0), axis=1) < 1).any():
        raise ValueError('Choose distinct trace points.')
    w = trace_width(gray, ridge, pts)
    f = np.asarray(gray, np.float32)          # oriented kernels are zero-mean: no flat-field needed
    P = ridge.get('P')
    pieces, heading = [pts[:1]], None
    for a, b in zip(pts[:-1], pts[1:]):
        piece, heading = track_segment(f, a, b, w, heading, P)
        pieces.append(piece[1:])
    c = finish_candidate(gray, ridge, np.vstack(pieces), 'trace', curve=TRACK_CURVE*w)
    c['learned'] = P is not None
    return c


MANUAL_MAX_POINTS = 500


def manual_line(gray, ridge, points):
    """The user's own polyline (straight segments through the clicks, nothing moved or smoothed); D is measured along it."""
    message = f'A line needs 2 to {MANUAL_MAX_POINTS} points inside the image.'
    height, width = ridge['R'].shape
    try:
        pts = np.asarray(points, float)
    except (TypeError, ValueError):
        raise ValueError(message)
    if pts.ndim != 2 or pts.shape[1] != 2 or not 2 <= len(pts) <= MANUAL_MAX_POINTS or not np.isfinite(pts).all()             or (pts < 0).any() or (pts[:, 0] >= width).any() or (pts[:, 1] >= height).any():
        raise ValueError(message)
    pts = pts[np.r_[True, np.linalg.norm(np.diff(pts, axis=0), axis=1) >= 1]]   # drop repeated clicks
    if len(pts) < 2: raise ValueError('Choose distinct line points.')
    c = finish_candidate(gray, ridge, pts, 'manual', curve=0)
    c['path'] = pts
    c['length_px'] = float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())
    c['learned'] = False
    return c


def stroke_map(ridge):
    """Ridge strength in [0, 1]: sato response, blended with the learned map like the tracker does."""
    S = np.clip(ridge['R']/max(float(np.percentile(ridge['R'], 99)), 1e-6), 0, 1)
    P = ridge.get('P')
    return S if P is None else (1-TRACK_LEARNED)*S+TRACK_LEARNED*P


def _along(S, c, direction, s):
    return ndi.map_coordinates(S, [c[1]+s*direction[1], c[0]+s*direction[0]], order=1, mode='nearest')


def _snap_across(S, c, tangent, reach):
    """c moved sideways (within +-reach px) onto the strongest ridge, with a mild preference for staying put."""
    t = np.arange(-reach, reach+.5, 1.)
    v = ndi.gaussian_filter1d(_along(S, c, [-tangent[1], tangent[0]], t), 1.)*(1-.3*np.abs(t)/max(reach, 1.))
    return c+t[int(np.argmax(v))]*np.array([-tangent[1], tangent[0]])


def _snap_tip(S, e, u, width):
    """End e (u: unit vector into the tube) drawn outside the tube (ridge below half its inner level) moves inwards to where the
    tube starts, at most STROKE_TIP widths. An end already on the tube stays: walking outwards to the ridge's drop measured worse
    than the user's own end (validation/cnt-stroke)."""
    s = np.arange(0, STROKE_TIP*width+.5, .5)
    r = ndi.gaussian_filter1d(_along(S, e, u, s), 1.)
    ref = float(np.median(_along(S, e, u, np.arange(.5*width, 1.5*width+.5, .5))))
    if ref < .05 or r[0] >= .5*ref: return e
    inside = np.flatnonzero(r >= .5*ref)
    return e+s[inside[0]]*u if len(inside) else e


def path_width(gray, ridge, g):
    """Tube width under a 1-px path: median profile width at 7 stations (sato scale if none measures)."""
    last = len(g)-1
    widths = []
    for i in np.rint(np.linspace(.1, .9, 7)*last).astype(int):
        r = width_at(gray, g[i], _unit(g[min(i+5, last)]-g[max(i-5, 0)]), ridge['um_per_pixel'], ridge['calibrated'])
        if r is not None: widths.append(r[0])
    return float(np.clip(np.median(widths) if widths else 2*float(np.median(ridge['sigma']))/SIGMA_PER_RADIUS, 6, 80))


def trace_stroke(gray, ridge, stroke):
    """Centerline under a freehand stroke (N, 2) xy in drawing order. The stroke is a guide, not the answer: the tracker
    runs piecewise between waypoints taken from it (moved onto the ridge), never leaves a corridor around it, and the two ends are
    the stroke's ends moved onto the ridge (and, when drawn off the tube, onto its tip): at most one tube width in total."""
    message = f'A stroke needs 2 to {STROKE_MAX_POINTS} points.'
    height, wide = ridge['R'].shape
    try:
        pts = np.asarray(stroke, float)
    except (TypeError, ValueError):
        raise ValueError(message)
    if pts.ndim != 2 or pts.shape[1] != 2 or not 2 <= len(pts) <= STROKE_MAX_POINTS or not np.isfinite(pts).all():
        raise ValueError(message)
    pts = np.clip(pts, 0, [wide-1, height-1])
    if np.linalg.norm(np.diff(pts, axis=0), axis=1).sum() < 1:
        raise ValueError('Draw a stroke with at least 2 distinct points along the tube.')
    g = smooth_path(resample(pts), STROKE_GUIDE_WINDOW)
    last = len(g)-1
    tangent = lambda i: _unit(g[min(i+5, last)]-g[max(i-5, 0)])
    w = path_width(gray, ridge, g)
    radius = max(STROKE_CORRIDOR*w, STROKE_CORRIDOR_MIN)
    S = stroke_map(ridge)
    cuts = np.rint(np.linspace(0, last, max(1, int(round(last/(STROKE_SPACING*w))))+1)).astype(int)
    marks = [_snap_across(S, g[i], tangent(i), min(STROKE_SNAP*w, radius)) for i in cuts]
    for k, i, toward in ((0, 0, min(int(round(w)), last)), (-1, last, max(last-int(round(w)), 0))):  # ends: off-tube ends move onto the tip
        e = _snap_tip(S, marks[k], _unit(g[toward]-g[i]), w)
        marks[k] = g[i]+(e-g[i])*min(1., w/max(float(np.linalg.norm(e-g[i])), 1e-9))
    f = np.asarray(gray, np.float32)
    P = ridge.get('P')
    pieces, heading = [marks[0][None]], None
    for n, (a, b) in enumerate(zip(marks[:-1], marks[1:])):
        piece, heading = track_segment(f, a, b, w, heading, P, np.vstack([a, g[cuts[n]:cuts[n+1]+1], b]), radius)
        pieces.append(piece[1:])
    # The line is the drag itself: trimmed where the tracker found the tube ends, nudged toward the tracked centre by at most
    # STROKE_PULL widths (smoothly), so it never cuts across a bundle or a bend the user drew around.
    raw = resample(np.vstack(pieces))
    i0, i1 = (int(np.argmin(np.linalg.norm(g-m, axis=1))) for m in (marks[0], marks[-1]))
    line = g[i0:i1+1] if i1-i0 >= 2 else g
    near = raw[cKDTree(raw).query(line)[1]]
    pull = np.column_stack([ndi.gaussian_filter1d(near[:, k]-line[:, k], max(STROKE_PULL_SIGMA*w, 1.), mode='nearest') for k in (0, 1)])
    size = np.linalg.norm(pull, axis=1, keepdims=True)
    line = line+pull*np.minimum(1, STROKE_PULL*w/np.maximum(size, 1e-9))
    c = finish_candidate(gray, ridge, line, 'trace', curve=STROKE_CURVE*w)
    c['learned'] = P is not None
    c['end_shift'] = [float(np.linalg.norm(c['path'][0]-pts[0])), float(np.linalg.norm(c['path'][-1]-pts[-1]))]   # diagnostics only
    return c


def measure_mask(gray, mask, ridge):
    raw = geometry(mask, compact_fallback=False)['length_path']
    if len(raw) < 2:
        raise ValueError('Cannot trace a centerline in this object.')
    return finish_candidate(gray, ridge, raw, 'sam')
