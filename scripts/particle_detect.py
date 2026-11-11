"""Flake/particle length and width from a mask, and the rules that decide which SAM masks are measurable particles.

Length = maximum Feret diameter on the outline (pixel corners). Width = the Feret diameter perpendicular to the length (caliper: max minus
min projection of the outline on the length's normal); the outline-to-outline chord through the middle of the length line is kept as width_chord_px."""
import cv2
import numpy as np
from scipy import ndimage as ndi

REF_UM_PER_PX = 931/1024   # 300x: the px thresholds below were set on this scale and are converted with the image's um_per_pixel
RIM_MIN = 8                # not_particle: outline ring (1 px) minus local background, grey levels
MIN_AREA_UM2 = 600*REF_UM_PER_PX**2   # small: 600 px at 300x (~25 um equivalent diameter)
BORDER_UM = 3*REF_UM_PER_PX           # cut_off: a mask pixel closer than this to the image edge (= analysis bottom)
BG_WINDOW_UM = 101*REF_UM_PER_PX      # median-filter window of the local background
CONTACT_FRAC = .20         # overlapped: outline fraction within 3 px of another particle mask
SOLIDITY = .80             # overlapped_shape: area / convex-hull area
STAND_ASPECT = 3.0         # standing: Feret L / chord W above this ...
STAND_BRIGHT = 50          # ... or interior mean minus background above this
FEATURE_KEYS = ('contact', 'solidity', 'aspect', 'rim', 'interior')   # stored with each particle
REASONS = ('cut_off', 'overlapped', 'overlapped_shape', 'standing', 'not_particle', 'small')
CORNERS = np.array([[-.5, -.5], [-.5, .5], [.5, -.5], [.5, .5]])
SAM_SETTINGS = dict(points_per_side=16, pred_iou_thresh=.7, stability_score_thresh=.85, crop_n_layers=0, min_mask_region_area=0, output_mode='binary_mask')


def chord(mask, c, n, step=.25):
    """Outline-to-outline length of the line through c along n: the run of mask pixels holding c (or nearest to it)."""
    r = np.hypot(*mask.shape)
    t = np.arange(-r, r+step, step); P = c+t[:, None]*n
    ok = (P[:, 0] >= 0) & (P[:, 1] >= 0) & (P[:, 0] < mask.shape[1]-.5) & (P[:, 1] < mask.shape[0]-.5)
    inside = np.zeros(len(t), bool); q = np.round(P[ok]).astype(int); inside[ok] = mask[q[:, 1], q[:, 0]]
    if not inside.any(): return 0., None
    k = int(np.argmin(np.where(inside, abs(t), 1e9)))
    lo = hi = k
    while lo > 0 and inside[lo-1]: lo -= 1
    while hi < len(t)-1 and inside[hi+1]: hi += 1
    return float(t[hi]-t[lo]+1), (P[lo]-n*.5, P[hi]+n*.5)


def feret_measure(mask):
    cs, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    pts = (np.concatenate(cs).reshape(-1, 2).astype(float)[:, None, :]+CORNERS[None]).reshape(-1, 2)
    h = cv2.convexHull(pts.astype(np.float32)).reshape(-1, 2).astype(float)
    dd = np.linalg.norm(h[:, None]-h[None], axis=2); i, j = np.unravel_index(dd.argmax(), dd.shape)
    a, b = h[i], h[j]; d = (b-a)/dd[i, j]; n = np.array([-d[1], d[0]])
    p = h@n; lo, hi = p.argmin(), p.argmax()
    chord_px, line = chord(mask, (a+b)/2, n)
    caliper = float(p[hi]-p[lo])
    s = ((h[lo]+h[hi])/2)@d   # along the length: midway between the two extreme outline points
    line = (d*s+n*p[lo], d*s+n*p[hi])
    return dict(length_px=float(dd[i, j]), length_line=[a.tolist(), b.tolist()], width_px=caliper, width_line=[line[0].tolist(), line[1].tolist()],
                width_caliper_px=caliper, width_chord_px=chord_px or caliper, solidity=float(mask.sum()/max(cv2.contourArea(h.astype(np.float32)), 1)))


def particle_features(masks, gray, um_per_pixel=REF_UM_PER_PX, others=()):
    """One dict per mask for the rules (`others`: masks of already measured particles that count as neighbours but get no row)."""
    H, W = gray.shape; um2 = um_per_pixel**2
    min_area, border = round(MIN_AREA_UM2/um2), max(1, round(BORDER_UM/um_per_pixel))
    bg = cv2.medianBlur(gray, max(3, min(round(BG_WINDOW_UM/um_per_pixel), min(H, W)-1)//2*2+1)).astype(np.float32)
    k3, k7 = np.ones((3, 3), np.uint8), np.ones((7, 7), np.uint8)
    owner, rims = np.zeros(gray.shape, np.int32), []
    for k, m in enumerate([*masks, *others], 1):
        m8 = m.astype(np.uint8); ero = cv2.erode(m8, k3).astype(bool); ring = cv2.dilate(m8, k3).astype(bool) & ~ero; edge = m & ~ero
        rims.append(float(gray[edge].mean()-bg[edge].mean()) if edge.any() else 0.)
        # neighbours for the contact test: not background masks (they enclose other masks) and not substrate blobs
        if m.sum() < .2*m.size and ndi.binary_fill_holes(m).sum() < 1.3*m.sum() and ring.any() and float(gray[ring].mean()-bg[ring].mean()) >= RIM_MIN: owner[m] = k
    rows = []
    for k, m in enumerate(masks, 1):
        area = int(m.sum()); f = feret_measure(m)
        if area < min_area: rows.append(dict(small=True, area=area, feret=f)); continue
        yy, xx = np.nonzero(m)
        edge = m & ~cv2.erode(m.astype(np.uint8), k3).astype(bool)
        near = cv2.dilate(((owner > 0) & (owner != k)).astype(np.uint8), k7).astype(bool)
        inner = cv2.erode(m.astype(np.uint8), k7).astype(bool)
        rows.append(dict(small=False, area=area, cut_off=bool(min(xx.min(), yy.min(), W-1-xx.max(), H-1-yy.max()) < border),
            contact=float((edge & near).sum()/max(edge.sum(), 1)), solidity=f['solidity'], aspect=f['length_px']/max(f['width_chord_px'], 1),   # the rule keeps its chord-width basis
            rim=rims[k-1], interior=float(gray[inner].mean()-bg[inner].mean()) if inner.any() else 0., feret=f))
    return rows


def exclusion_reason(f):
    if f['small']: return 'small'
    if f['rim'] < RIM_MIN: return 'not_particle'
    if f['cut_off']: return 'cut_off'
    if f['contact'] > CONTACT_FRAC: return 'overlapped'
    if f['solidity'] < SOLIDITY: return 'overlapped_shape'
    if f['aspect'] > STAND_ASPECT or f['interior'] > STAND_BRIGHT: return 'standing'


def detect_particles(gray, proposals, um_per_pixel=REF_UM_PER_PX):
    """(kept, counts): kept = feature dicts (with `mask`) of the proposals that pass every rule; counts per exclusion reason."""
    counts, kept = dict.fromkeys(REASONS, 0), []
    for m, f in zip(proposals, particle_features(proposals, gray, um_per_pixel)):
        reason = exclusion_reason(f)
        if reason: counts[reason] += 1
        else: kept.append(dict(f, mask=m))
    return kept, counts


def resolve_proposals(proposals, shape, min_area=100):
    """SAM automatic proposals -> exclusive masks, smallest first (as the Labeling run does); background masks are dropped."""
    masks, occupied = [], np.zeros(shape, bool)
    for p in sorted(proposals, key=lambda p: (p['area'], -p['predicted_iou'])):
        m = p['segmentation'].astype(bool)
        if m.mean() > .8 or p['area'] < min_area: continue
        k = m & ~occupied
        if k.sum() < min_area or k.sum() < .5*m.sum(): continue
        masks.append(k); occupied |= k
    return masks
