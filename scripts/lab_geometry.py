"""General 2-D object measurements, in original image coordinates.

Length is the diameter of the weighted skeleton forest after breaking cycles
with a minimum spanning tree. Width is minimum Feret width of pixel cells.
Disconnected masks use their longest component for length and all pixels for
Feret width. These definitions deliberately do not assume a object or ellipse.
"""
import cv2
import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import connected_components, dijkstra, minimum_spanning_tree
from skimage.morphology import skeletonize


def geometry(mask, compact_fallback=True, extend_ends=True):
    yy, xx = np.nonzero(mask)
    if not len(xx):
        raise ValueError('Cannot measure an empty object.')
    x0, y0 = int(xx.min()), int(yy.min())
    crop = mask[y0:int(yy.max())+1, x0:int(xx.max())+1]
    skeleton = skeletonize(np.pad(crop, 1))[1:-1, 1:-1]
    sy, sx = np.nonzero(skeleton)
    if not len(sx):
        sy, sx = np.array([int(np.median(yy))-y0]), np.array([int(np.median(xx))-x0])
    indices = np.full(crop.shape, -1, np.int32)
    indices[sy, sx] = np.arange(len(sx))
    rows, cols, weights = [], [], []
    for dy, dx in [(0, 1), (1, -1), (1, 0), (1, 1)]:
        ny, nx = sy + dy, sx + dx
        valid = (ny >= 0) & (ny < crop.shape[0]) & (nx >= 0) & (nx < crop.shape[1])
        src = np.flatnonzero(valid)
        dst = indices[ny[valid], nx[valid]]
        keep = dst >= 0
        rows.extend(src[keep]); cols.extend(dst[keep])
        weights.extend([float(np.hypot(dx, dy))] * int(keep.sum()))
    graph = sparse.csr_matrix((weights, (rows, cols)), shape=(len(sx), len(sx)))
    forest = minimum_spanning_tree(graph + graph.T)
    forest = (forest + forest.T).tocsr()
    degrees = np.diff((graph + graph.T).tocsr().indptr)
    count, components = connected_components(forest, directed=False)
    best_length, best_path = 0., [0]
    for component in range(count):
        members = np.flatnonzero(components == component)
        distances = dijkstra(forest, directed=False, indices=int(members[0]))
        start = int(members[np.argmax(distances[members])])
        distances, previous = dijkstra(forest, directed=False, indices=start, return_predecessors=True)
        end = int(members[np.argmax(distances[members])])
        if distances[end] >= best_length:
            best_length = float(distances[end]); best_path = [end]
            while best_path[-1] != start:
                best_path.append(int(previous[best_path[-1]]))
    path = np.column_stack((sx[best_path] + x0, sy[best_path] + y0)).astype(float)
    contours, _ = cv2.findContours(crop.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    hull = cv2.convexHull(np.concatenate(contours)).reshape(-1, 2).astype(float)
    hull += [x0, y0]
    # Rotating calipers: maximum straight Feret diameter, also a meaningful
    # longitudinal dimension for compact objects whose skeleton is just a point.
    farthest = (0., hull[0], hull[0])
    if len(hull) > 1:
        j = 1
        cross = lambda a,b: float(a[0]*b[1]-a[1]*b[0])
        for i in range(len(hull)):
            edge = hull[(i+1)%len(hull)]-hull[i]
            for _ in range(len(hull)):
                if abs(cross(edge,hull[(j+1)%len(hull)]-hull[i])) <= abs(cross(edge,hull[j]-hull[i]))+1e-10: break
                j = (j+1)%len(hull)
            for endpoint in (hull[i],hull[(i+1)%len(hull)]):
                distance = float(np.linalg.norm(endpoint-hull[j]))
                if distance > farthest[0]: farthest = (distance, endpoint, hull[j])
    diameter, a, b = farthest
    direction = (b-a)/diameter if diameter else np.array([1.,0.])
    half_cell = .5*np.abs(direction).sum()
    max_feret = diameter+2*half_cell
    feret_line = np.array([a-direction*half_cell,b+direction*half_cell])
    vectors = np.roll(hull, -1, axis=0) - hull
    vectors = vectors[np.linalg.norm(vectors, axis=1) > 0]
    normals = np.vstack(([1., 0.], [0., 1.], np.column_stack((-vectors[:, 1], vectors[:, 0]))))
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    # Include half a pixel on either side so 1-pixel masks have finite width.
    best = None
    for normal in normals:
        projections = hull @ normal
        half = .5 * np.abs(normal).sum()
        low, high = float(projections.min()-half), float(projections.max()+half)
        if best is None or high-low < best[0]:
            tangent = np.array([-normal[1], normal[0]])
            middle = float(np.median(hull @ tangent))
            best = (high-low, [normal*low+tangent*middle, normal*high+tangent*middle])
    method = 'centerline_with_boundary_extension'
    if compact_fallback and count == 1 and (best_length < best[0] or len(path) < 2):
        # A disk or compact particle has no stable elongated centerline.
        best_length, path, method = max_feret, feret_line, 'max_feret_compact_object'
    elif extend_ends and len(path) > 1:
        # Reach the visible object boundary rather than stop at skeleton centers.
        for at_start in (True, False):
            endpoint = path[0] if at_start else path[-1]
            inner = path[min(8,len(path)-1)] if at_start else path[max(0,len(path)-9)]
            vector = endpoint-inner
            norm = np.linalg.norm(vector)
            if norm == 0: continue
            vector /= norm
            last = endpoint.copy()
            for step in np.arange(.5, np.hypot(*crop.shape)+1, .5):
                sample = endpoint+step*vector
                px, py = np.floor(sample+.5).astype(int)
                if px<0 or py<0 or py>=mask.shape[0] or px>=mask.shape[1] or not mask[py,px]: break
                last = sample
            best_length += float(np.linalg.norm(last-endpoint))
            if at_start: path = np.vstack((last,path))
            else: path = np.vstack((path,last))
    return dict(length_pixels=best_length, width_pixels=float(best[0]),
                length_path=path.tolist(), width_line=np.asarray(best[1]).tolist(),
                max_feret_pixels=max_feret, min_feret_pixels=float(best[0]), length_method=method,
                skeleton_components=int(count), skeleton_branch_pixels=int((degrees > 2).sum()),
                skeleton_cycles_cut=int(len(weights)-forest.nnz//2))


def object_path(mask, endpoints):
    """Shortest 8-connected path within the selected mask; no background bridges."""
    from skimage.graph import MCP_Geometric
    yy, xx = np.nonzero(mask)
    if not len(xx):
        raise ValueError('The selected object is empty.')
    points = np.asarray(endpoints, dtype=float)
    if points.shape != (2, 2) or not np.isfinite(points).all():
        raise ValueError('Choose two endpoints.')
    snapped = []
    for x, y in points:
        distances = (xx-x)**2+(yy-y)**2
        nearest = int(np.argmin(distances))
        if distances[nearest] > 25:
            raise ValueError('Place both endpoints on the selected object (within 5 pixels).')
        snapped.append((int(yy[nearest]), int(xx[nearest])))
    if snapped[0] == snapped[1]:
        raise ValueError('Choose two distinct points on the object.')
    y0, x0 = int(yy.min()), int(xx.min())
    cropped = mask[y0:int(yy.max())+1, x0:int(xx.max())+1]
    start, end = [(y-y0, x-x0) for y, x in snapped]
    solver = MCP_Geometric(np.where(cropped, 1., np.inf), fully_connected=True)
    costs, _ = solver.find_costs([start], [end])
    if not np.isfinite(costs[end]):
        raise ValueError('These endpoints are on disconnected parts. Correct the mask or draw a path manually.')
    path = np.asarray(solver.traceback(end), dtype=float)
    return np.column_stack((path[:, 1]+x0, path[:, 0]+y0))


def centered_geometry(mask):
    """Automatic arc-midpoint and local normal width, entirely inside the object."""
    from scipy.ndimage import distance_transform_edt
    g = geometry(mask, compact_fallback=False)
    path = np.asarray(g['length_path'], dtype=float)
    def inside(p):
        x, y = np.floor(p+.5).astype(int)
        return 0 <= y < mask.shape[0] and 0 <= x < mask.shape[1] and mask[y, x]
    def ray(center, direction):
        last = center.copy()
        for step in np.arange(.25, np.hypot(*mask.shape)+1, .25):
            point = center+step*direction
            if not inside(point): break
            last = point
        return last
    arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
    if len(path) < 2 or arc[-1] < 2:
        # Compact objects have no stable elongated skeleton. Use an interior
        # distance maximum and the principal axis, clipped to the same mask.
        padded = np.pad(mask, 1)
        distances = distance_transform_edt(padded)[1:-1, 1:-1]
        y, x = np.unravel_index(distances.argmax(), mask.shape)
        center = np.array([x, y], dtype=float)
        yy, xx = np.nonzero(mask)
        coords = np.column_stack((xx, yy)).astype(float)
        centered = coords-coords.mean(axis=0)
        _, vectors = np.linalg.eigh(centered.T@centered)
        tangent = vectors[:, -1]
        path = np.array([ray(center, -tangent), center, ray(center, tangent)])
        g['length_method'] = 'automatic_interior_principal_axis'
    else:
        middle = arc[-1]/2
        center = np.array([np.interp(middle, arc, path[:, k]) for k in (0, 1)])
        span = min(5., arc[-1]/4)
        before = np.array([np.interp(middle-span, arc, path[:, k]) for k in (0, 1)])
        after = np.array([np.interp(middle+span, arc, path[:, k]) for k in (0, 1)])
        tangent = after-before
        if np.linalg.norm(tangent) < 1e-8:
            i = min(len(path)-2, max(0, int(np.searchsorted(arc, middle)-1)))
            tangent = path[i+1]-path[i]
        tangent /= np.linalg.norm(tangent)
        g['length_method'] = 'automatic_centerline_arc_midpoint'
    normal = np.array([-tangent[1], tangent[0]])
    width = np.array([ray(center, -normal), center, ray(center, normal)])
    g.update(length_path=path.tolist(), length_pixels=float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum()),
             center_point=center.tolist(), width_line=width.tolist(),
             width_pixels=float(np.linalg.norm(np.diff(width, axis=0), axis=1).sum()))
    return g


def automatic_center(mask, automatic=None):
    g = automatic if automatic is not None else centered_geometry(mask)
    point = np.asarray(g['center_point'])
    yy, xx = np.nonzero(mask)
    nearest = np.argmin((xx-point[0])**2+(yy-point[1])**2)
    return np.array([xx[nearest], yy[nearest]], dtype=float)


def center_connected_path(mask, endpoints, center=None):
    """The two user endpoints share one automatically selected center waypoint."""
    points = np.asarray(endpoints, dtype=float)
    if points.shape != (2, 2):
        raise ValueError('Choose two endpoints.')
    center = automatic_center(mask) if center is None else np.asarray(center)
    pieces = []
    for point in points:
        if np.linalg.norm(point-center) < .5:
            pieces.append(np.array([center]))
        else:
            pieces.append(object_path(mask, [point, center]))
    return np.vstack((pieces[0], pieces[1][-2::-1]))


def report_geometry(mask, annotation, automatic=None):
    result = dict(automatic if automatic is not None else centered_geometry(mask))
    center = automatic_center(mask, result)
    paths = dict(annotation.get('manual_measurements', {}))
    for axis, method in annotation.get('measurement_methods', {}).items():
        if method in ('object_path', 'object_path_via_center') and len(paths.get(axis, [])) > 1:
            path = paths[axis]
            paths[axis] = center_connected_path(mask, [path[0], path[-1]], center).tolist()
    result.update(manual_geometry(dict(manual_measurements=paths)))
    result['center_point'] = center.tolist()
    return result


def manual_geometry(annotation):
    """Lengths are sums along the user's sampled path, never an endpoint chord."""
    paths = annotation.get('manual_measurements', {})
    length = paths.get('length', [])
    width = paths.get('width', [])
    def distance(path):
        return float(np.linalg.norm(np.diff(np.asarray(path, dtype=float), axis=0), axis=1).sum()) if len(path) > 1 else float('nan')
    return dict(length_pixels=distance(length), width_pixels=distance(width),
                length_path=length, width_line=width, length_method='manual_path')


TUBE_COLOR = '#ffff00'      # matches the hand-labelled CNT figures: pure yellow, 1 px aliased lines
TUBE_FONT_RATIO = 21/16     # Arial 21 px at the default Text size 16 (cap height ~15 px)


def tube_width_segments(line):
    """Hand-label width style: two lines along the tube through the width ends, '+' at the middle."""
    a, b = np.asarray(line[0], float), np.asarray(line[-1], float)
    across = b-a
    width = float(np.linalg.norm(across))
    if width <= 0: return []
    along = np.array([-across[1], across[0]])/width
    half = max(12., width)  # each edge line is ~2x the width long
    mid, arm = (a+b)/2, max(5., .3*width)
    return [(end-along*half, end+along*half) for end in (a, b)] + [(mid-along*arm, mid+along*arm), (mid-across/width*arm, mid+across/width*arm)]


def tube_edge_segments(edges):
    """A D drawn as two parallel lines (hand-label style): both lines as drawn, a dotted connector between their middles, '+'."""
    (a0, a1), (b0, b1) = (np.asarray(e, float) for e in edges)
    m0, m1 = (a0+a1)/2, (b0+b1)/2
    across = m1-m0; width = float(np.linalg.norm(across))
    if width <= 0: return [(a0, a1), (b0, b1)]
    u = across/width; along = np.array([-u[1], u[0]])
    dots = [(m0+u*s, m0+u*min(s+2, width)) for s in np.arange(0, width, 5)]
    mid, arm = (m0+m1)/2, max(5., .3*min(width, 30.))
    return [(a0, a1), (b0, b1)] + dots + [(mid-along*arm, mid+along*arm), (mid-u*arm, mid+u*arm)]


def particle_segments(line, cap=9., touch=None):
    """Particle style: the straight line plus a perpendicular cap centred on each end. The two caps are parallel and equally long.
    `touch` = the outline points the tangents of a Feret width rest on: the caps then reach them, so each end line touches the particle."""
    a, b = np.asarray(line[0], float), np.asarray(line[-1], float)
    along = (b-a)/max(float(np.linalg.norm(b-a)), 1e-9)
    across = np.array([-along[1], along[0]])
    half = cap/2
    if touch is not None and len(touch) == 2:
        t = np.asarray(touch, float)
        if abs((t[0]-a)@along) <= 1.5 and abs((t[1]-b)@along) <= 1.5:   # still this line's tangent points (a redrawn line has none)
            half = max(half, abs((t[0]-a)@across)+1, abs((t[1]-b)@across)+1)
    return [(a, b)]+[(end-across*half, end+across*half) for end in (a, b)]


LABEL_PAD = 2                  # blank margin inside a label box, px
LABEL_GAPS = ((5, 8, 12), (18, 28, 45, 70))   # offsets from the own line; the second set is the far fallback
LABEL_DIRECTIONS = 12
LABEL_CLEAR_OTHER = 3          # min distance from a label to any foreign drawn line
LABEL_CLEAR_OWN = 4            # min distance from a label to its own line
LABEL_AMBIGUITY = (2., 15.)    # nearest foreign line must be >= max(2 x own distance, own distance + 15 px)
LABEL_NEIGHBOUR = 1.5          # a box closer than this many text heights to another label is penalised
LABEL_NEIGHBOUR_PENALTY = 20.
LABEL_ANCHOR_WEIGHT = .04      # cost per px from the preferred anchor point


def raster_segments(segments, shape):
    image = np.zeros(shape, np.uint8)
    for p, q in segments:
        cv2.line(image, tuple(int(round(v)) for v in p), tuple(int(round(v)) for v in q), 1, 1)
    return image.astype(bool)


def distance_to(raster):
    if not raster.any(): return np.full(raster.shape, 1e4, np.float32)
    return cv2.distanceTransform((~raster).astype(np.uint8), cv2.DIST_L2, 3)


def place_tube_label(size, own_segments, own_raster, others, foreign, blocked, boxes, anchor):
    """Text box (x0, y0, ambiguous) for one tube label, or None.

    Candidates sit beside the label's OWN line (both sides, ends, diagonals) at a small gap. A box must be inside the
    image and clear of every mask, drawn line (`others`) and placed label. It is unambiguous when the nearest line of
    ANOTHER tube (`foreign`) is much farther than its own line; only without such a spot is the closest valid box used (the caller adds a leader line),
    and when no box near its own line is free at all, the closest free box anywhere. None only when the image has no free box."""
    from scipy import ndimage as ndi
    bh, bw = size
    height, width = blocked.shape
    if bh > height or bw > width: return None
    boxed = blocked.copy()
    labels = np.zeros(blocked.shape, bool)
    for x0, y0, x1, y1 in boxes:
        boxed[max(y0, 0):y1, max(x0, 0):x1] = True; labels[max(y0, 0):y1, max(x0, 0):x1] = True
    integral = cv2.integral(boxed.astype(np.uint8))
    overlap = integral[bh:, bw:]-integral[:-bh, bw:]-integral[bh:, :-bw]+integral[:-bh, :-bw]   # indexed by top-left
    rows, cols = height-bh+1, width-bw+1
    least = lambda dist: ndi.minimum_filter(dist, size=(bh, bw), mode='constant', cval=1e4)[bh//2:bh//2+rows, bw//2:bw//2+cols]
    d_own, d_other, d_foreign, d_label = (least(distance_to(r)) for r in (own_raster, others, foreign, labels))
    usable = (overlap == 0) & (d_other >= LABEL_CLEAR_OTHER) & (d_own >= LABEL_CLEAR_OWN)
    if not usable.any(): return None
    angles = np.deg2rad(np.arange(LABEL_DIRECTIONS)*360/LABEL_DIRECTIONS)
    fallback = None
    for gaps in LABEL_GAPS:
        candidates = set()
        for p, q in own_segments:
            for c in p+(q-p)*np.linspace(0, 1, max(1, int(np.ceil(np.linalg.norm(q-p)/6)))+1)[:, None]:
                for gap in gaps:
                    for t in angles:
                        reach = gap+abs(np.cos(t))*bw/2+abs(np.sin(t))*bh/2
                        x0, y0 = int(round(c[0]+np.cos(t)*reach-bw/2)), int(round(c[1]+np.sin(t)*reach-bh/2))
                        if 0 <= x0 < cols and 0 <= y0 < rows and usable[y0, x0]: candidates.add((x0, y0))
        scored = []
        for x0, y0 in candidates:
            near, far = float(d_own[y0, x0]), float(d_foreign[y0, x0])
            cost = near+LABEL_ANCHOR_WEIGHT*float(np.hypot(x0+bw/2-anchor[0], y0+bh/2-anchor[1]))
            if d_label[y0, x0] < LABEL_NEIGHBOUR*bh: cost += LABEL_NEIGHBOUR_PENALTY
            scored.append((far < max(LABEL_AMBIGUITY[0]*near, near+LABEL_AMBIGUITY[1]), cost, x0, y0))
        clear = [c for c in scored if not c[0]]
        if clear:
            _, _, x0, y0 = min(clear)
            return x0, y0, False
        if scored and fallback is None:
            _, _, x0, y0 = min(scored, key=lambda c: c[1])
            fallback = (x0, y0, True)
    if fallback is None:  # crowded: every spot near its own line is taken, so use the free spot closest to it (the caller adds a leader line)
        ys, xs = np.nonzero(usable)
        i = int(np.argmin(d_own[ys, xs]+LABEL_ANCHOR_WEIGHT*np.hypot(xs+bw/2-anchor[0], ys+bh/2-anchor[1])))
        fallback = (int(xs[i]), int(ys[i]), True)
    return fallback


def place_tube_labels(draw, font, tube_lines, union, occupied):
    """Place T#/D# labels beside their own lines: crowded objects first, a leader only when no unambiguous spot exists."""
    from PIL import ImageDraw
    if not tube_lines: return
    shape = union.shape
    rasters = {key: raster_segments(segments, shape) for key, (segments, _, _) in tube_lines.items()}
    items = []
    for key, (segments, text, anchor) in tube_lines.items():
        others, foreign = np.zeros(shape, bool), np.zeros(shape, bool)
        for other, raster in rasters.items():
            if other == key: continue
            others |= raster
            if other[0] != key[0]: foreign |= raster
        bounds = draw.textbbox((0, 0), text, font=font)
        crowd = float(distance_to(foreign)[rasters[key]].min()) if foreign.any() else 1e9
        items.append((crowd, key, segments, text, anchor, bounds, others, foreign))
    for crowd, key, segments, text, anchor, bounds, others, foreign in sorted(items, key=lambda i: (i[0], i[1])):
        bw, bh = bounds[2]-bounds[0]+2*LABEL_PAD, bounds[3]-bounds[1]+2*LABEL_PAD
        found = place_tube_label((bh, bw), segments, rasters[key], others, foreign, union, occupied, anchor)
        if found is None:
            raise ValueError('No space outside the object for measurement text. Reduce Text size or hide IDs.')
        x0, y0, ambiguous = found
        occupied.append((x0, y0, x0+bw, y0+bh))
        draw.text((x0+LABEL_PAD-bounds[0], y0+LABEL_PAD-bounds[1]), text, fill=TUBE_COLOR, font=font)
        if ambiguous:  # no spot is clearly closer to its own line than to a foreign one: tie the label to its line
            samples = np.vstack([p+(q-p)*np.linspace(0, 1, max(2, int(np.linalg.norm(q-p)/2)))[:, None] for p, q in segments])
            inner = np.array([[x0+LABEL_PAD, y0+LABEL_PAD], [x0+bw-LABEL_PAD, y0+bh-LABEL_PAD]], float)
            edge = np.clip(samples, inner[0], inner[1])
            nearest = int(np.argmin(np.linalg.norm(samples-edge, axis=1)))
            draw.line([tuple(edge[nearest]), tuple(samples[nearest])], fill=TUBE_COLOR, width=1)


def measured_overlay(state, opacity=.18, show_length=True, show_width=True, show_ids=True, font_size=16):
    """RGB full-resolution figure, with yellow paths, width lines and text."""
    from PIL import Image, ImageDraw, ImageFont
    from pathlib import Path
    pixels = state.get('rgb', np.repeat(state['gray'][:, :, None], 3, axis=2)).copy()
    annotations = state.get('annotations', {})
    is_tube = lambda identifier: 'tube' in annotations.get(str(identifier), {}) or 'particle' in annotations.get(str(identifier), {})   # no fill, no outline
    for identifier, mask in state['masks'].items():
        if is_tube(identifier): continue  # tube figures match the hand-labelled style: no fill, no outline
        pixels[mask] = np.rint((1-opacity)*pixels[mask]+opacity*np.array([255, 215, 0])).astype(np.uint8)
        contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(pixels, contours, -1, (255, 215, 0), 1)
    figure = Image.fromarray(pixels); draw = ImageDraw.Draw(figure)
    font_path = Path('C:/Windows/Fonts/arial.ttf')
    font = ImageFont.truetype(str(font_path), int(font_size)) if font_path.exists() else ImageFont.load_default()
    tube_font = ImageFont.truetype(str(font_path), int(round(font_size*TUBE_FONT_RATIO))) if font_path.exists() else font
    scale = state['report']['scale']['um_per_pixel']
    unit = state['report'].get('measurement_unit', 'µm')
    cache = state.setdefault('geometry_cache', {})
    occupied, tube_lines = [], {}
    union = np.zeros(state['gray'].shape, np.uint8)
    for mask in state['masks'].values(): union |= mask.astype(np.uint8)
    def label(text, anchor, mask, tube=False):
        f, stroke = (tube_font, 0) if tube else (font, 1)
        bounds = draw.textbbox((0, 0), text, font=f, stroke_width=stroke)
        width, height = bounds[2]-bounds[0], bounds[3]-bounds[1]
        # Search empty rectangles, not just a label's center: every glyph must
        # remain outside the object, even for curved and concave masks.
        bw, bh = int(width+8), int(height+8)
        chosen = None
        for obstruction in (union, mask.astype(np.uint8)):
            blocked = obstruction.copy()
            for a,b,c,d in occupied: blocked[b:d,a:c] = 1
            if bw > figure.width or bh > figure.height: break
            integral = cv2.integral(blocked)
            sums = integral[bh:,bw:]-integral[:-bh,bw:]-integral[bh:,:-bw]+integral[:-bh,:-bw]
            ys, xs = np.nonzero(sums == 0)
            if len(xs):
                nearest = np.argmin((xs+bw/2-anchor[0])**2+(ys+bh/2-anchor[1])**2)
                x, y = int(xs[nearest]), int(ys[nearest])
                chosen = (x+4, y+4, (x,y,x+bw,y+bh))
                break
        if chosen is None:
            raise ValueError('No space outside the object for measurement text. Reduce Text size or hide IDs.')
        x, y, box = chosen
        occupied.append(box)
        # Fine leader connects the outside value to its own measurement path.
        if tube:  # hand-label style: plain yellow text, no leader, no outline
            draw.text((x-bounds[0], y-bounds[1]), text, fill=TUBE_COLOR, font=f)
            return
        target = (max(x, min(anchor[0], x+width)), max(y, min(anchor[1], y+height)))
        draw.line([tuple(anchor), target], fill='#bfae35', width=1)
        draw.text((x-bounds[0], y-bounds[1]), text, fill='#ffed00', font=font,
                  stroke_width=1, stroke_fill='#161616')
    for identifier, mask in sorted(state['masks'].items()):
        key = (state['revision'], identifier)
        g = cache.get(key)
        particle = 'particle' in annotations.get(str(identifier), {})
        if particle: g = manual_geometry(annotations[str(identifier)])   # the straight lines as measured; no skeleton needed
        elif state['report'].get('workspace_mode') == 'report':
            if g is None: g = cache[key] = centered_geometry(mask)
            g = report_geometry(mask, state.get('annotations', {}).get(str(identifier), {}), g)
        elif g is None: g = cache[key] = geometry(mask)
        tube = is_tube(identifier)
        lines = []
        if show_length and len(g['length_path']) > 1:
            lines.append((g['length_path'], g['length_pixels'], .35, f'T{identifier}=' if tube and not particle else '', False))
        if show_width and len(g['width_line']) > 1:
            lines.append((g['width_line'], g['width_pixels'], .65, f'D{identifier}=' if tube and not particle else '', True))
        for line, value, fraction, prefix, is_width in lines:
            path = np.asarray(line, dtype=float)
            if tube:
                edges = state.get('annotations', {}).get(str(identifier), {}).get('width_edges')
                segments = particle_segments(path, touch=state.get('annotations', {}).get(str(identifier), {}).get('particle', {}).get('width_touch') if is_width else None) if particle else (tube_edge_segments(edges) if edges else tube_width_segments(path)) if is_width else list(zip(path[:-1], path[1:]))
                for p, q in segments: draw.line([tuple(p), tuple(q)], fill=TUBE_COLOR, width=1)
                if segments and np.isfinite(value):
                    arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
                    anchor = (path[0]+path[-1])/2 if is_width or particle else [np.interp(arc[-1]*fraction, arc, path[:, k]) for k in (0, 1)]
                    tube_lines[(identifier, 'D' if is_width else 'T')] = (segments, f'{prefix}{value*scale:.2f} {unit}', np.asarray(anchor, float))
                continue
            draw.line([tuple(p) for p in line], fill='#ffed00', width=2)
            # End caps follow each endpoint's local tangent, including curves.
            cap = max(8., font_size*.7)
            for end, candidates in [(path[0], path[1:]), (path[-1], path[-2::-1])]:
                for inner in candidates:
                    tangent = end-inner
                    norm = np.linalg.norm(tangent)
                    if norm > 1e-8:
                        normal = np.array([-tangent[1], tangent[0]])/norm
                        reaches = []
                        if tube:
                            # Measured on the whole tube, so the (possibly carved) mask must not size the caps.
                            reaches = [max(cap, .6*value) if is_width else cap]*2
                        for sign in (() if tube else (-1, 1)):
                            distance = 0.
                            for step in np.arange(.5, np.hypot(*mask.shape)+1, .5):
                                x, y = np.floor(end+sign*step*normal+.5).astype(int)
                                if not (0 <= y < mask.shape[0] and 0 <= x < mask.shape[1] and mask[y,x]): break
                                distance = step
                            reaches.append(max(cap, distance+.5))
                        draw.line([tuple(end-normal*reaches[0]), tuple(end+normal*reaches[1])], fill='#ffed00', width=2)
                        break
            if np.isfinite(value):
                arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
                anchor = [np.interp(arc[-1]*fraction, arc, path[:, k]) for k in (0, 1)]
                label(f'{prefix}{value*scale:.2f} {unit}', anchor, mask)
        if 'center_point' in g and (show_length or show_width) and not tube:
            cx, cy = g['center_point']
            draw.ellipse((cx-3, cy-3, cx+3, cy+3), fill='#ffed00', outline='#161616')
        yy, xx = np.nonzero(mask)
        x, y = float(xx.mean()), float(yy.mean())
        if show_ids and not (tube and (show_length or show_width)): label(f'#{identifier}', (x, y), mask)
    place_tube_labels(draw, tube_font, tube_lines, union.astype(bool), occupied)
    return figure
