import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import cv2
import numpy as np
import pytest
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
import cnt_detect
from cnt_detect import centerline_map, measure_mask, ridge_response, sigmas_for, trace_tube

UMP = .2725
T = np.linspace(0, 1, 400)
STRAIGHT = np.column_stack([100+500*T, 300+0*T])
SCURVE = np.column_stack([100+550*T, 300+120*np.sin(2*np.pi*T)])
CROSS = np.column_stack([400+0*T, 80+440*T])
FAR_SCURVE = SCURVE+[0, 150]


def arc(path):
    return float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum())


def render(curves, shape=(600, 800), ribbon=False, seed=0):
    img = np.full(shape, 50.)
    for path, width in curves:
        mask = np.zeros(shape, np.uint8)
        cv2.polylines(mask, [np.rint(path*4).astype(np.int32)], False, 1, int(width), cv2.LINE_8, shift=2)
        d = ndi.distance_transform_edt(mask)
        if ribbon: img = np.maximum(img, np.where(mask > 0, 110, 0)+np.where((d > 0) & (d < 3), 60, 0))
        else: img = np.maximum(img, 50+110*np.clip(d/1.5, 0, 1))
    img = ndi.gaussian_filter(img, 1)+np.random.default_rng(seed).normal(0, 6, shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def ridge_for(gray):
    return ridge_response(gray, UMP, True)


def assert_width(candidate, width):
    assert candidate['width_px'] is not None and abs(candidate['width_px']-width) <= .2*width+2


def end_trace(curve, width, ribbon=False, via=()):
    """Trace from the tube's two ends, as a user's two clicks would."""
    gray = render([(curve, width)], ribbon=ribbon)
    ridge = ridge_for(gray)
    ends = [curve[0].tolist(), *via, curve[-1].tolist()]
    ends = [[min(x, 799), min(y, 599)] for x, y in ends]
    c = trace_tube(gray, ridge, ends)
    assert abs(c['length_px']/arc(curve)-1) <= .06  # a trace cuts curve corners by a few percent
    assert np.mean(cKDTree(curve).query(c['path'])[0]) <= max(3, .3*width)  # stays inside the tube
    assert_width(c, width)
    return c


def test_sigmas_scale_with_calibration():
    values = [sigmas_for(.2725, True), sigmas_for(.0908, True), sigmas_for(1., False)]
    for s in values:
        assert len(s) == 5 and s == sorted(s) and 1.5 <= s[0] and s[-1] <= 20
    assert values[0][0] < values[1][0]


def test_straight_tube_trace():
    end_trace(STRAIGHT, 20)


def test_s_curve_trace_length_and_width():
    c = end_trace(SCURVE, 20)
    assert len(c['width_stations']) == 5
    p0, p1 = (np.asarray(p) for p in c['width_line'])
    assert cKDTree(SCURVE).query((p0+p1)/2)[0] <= 3
    assert cKDTree(SCURVE).query(p0)[0] > 3 and cKDTree(SCURVE).query(p1)[0] > 3


def test_ribbon_trace():
    end_trace(SCURVE, 24, ribbon=True)


def test_thin_trace():
    end_trace(SCURVE, 8)


def test_trace_with_waypoint():
    end_trace(SCURVE, 20, via=[SCURVE[200].tolist()])


def test_crossing_pair_trace_goes_straight():
    gray = render([(STRAIGHT, 20), (CROSS, 14)])
    c = trace_tube(gray, ridge_for(gray), [STRAIGHT[0].tolist(), STRAIGHT[-1].tolist()])
    assert abs(c['length_px']/arc(STRAIGHT)-1) <= .05
    assert np.median(cKDTree(STRAIGHT).query(c['path'])[0]) <= 3


def test_ribbon_with_crossing_fibre_stays_on_centre():
    # bright-edged ribbon (dark interior) crossed at 50 deg by a brighter fibre: stay on the ribbon's centre
    ribbon = np.column_stack([100+550*T, 260+80*T])
    fibre = np.column_stack([250+300*T, 520-440*T])
    gray = np.maximum(render([(ribbon, 26)], ribbon=True), render([(fibre, 12)], seed=1))
    c = trace_tube(gray, ridge_for(gray), [ribbon[0].tolist(), ribbon[-1].tolist()])
    d = cKDTree(ribbon).query(c['path'])[0]
    assert np.median(d) <= 2 and np.percentile(d, 90) <= 3 and d.max() <= 5
    assert abs(c['length_px']/arc(ribbon)-1) <= .03


def test_trace_validation():
    gray = render([(STRAIGHT, 20)])
    ridge = ridge_for(gray)
    good = STRAIGHT[0].tolist()
    for points in ([good], [good]*21, [good, [900, 10]], [good, good]):
        with pytest.raises(ValueError):
            trace_tube(gray, ridge, points)


def test_measure_mask_sam_fallback():
    gray = render([(SCURVE, 20)])
    mask = np.zeros(gray.shape, np.uint8)
    cv2.polylines(mask, [np.rint(SCURVE).astype(np.int32)], False, 1, 20)
    c = measure_mask(gray, mask.astype(bool), ridge_for(gray))
    assert abs(c['length_px']/(arc(SCURVE)+20)-1) <= .03
    assert_width(c, 20)


def make_state(gray):
    return dict(dataset='t', gray=gray, rgb=np.repeat(gray[:, :, None], 3, axis=2),
        report=dict(workspace_mode='report', image='x.png', scale=dict(um_per_pixel=UMP), measurement_unit='µm'),
        masks={}, annotations={}, history=[], next_id=1, revision=0)


def test_trace_overlay_export_undo(tmp_path):
    from lab_editor import LabEditor
    from lab_geometry import manual_geometry, measured_overlay, report_geometry
    editor = LabEditor(output_root=tmp_path/'edits', project_root=tmp_path/'projects', device='cpu')
    first, second = STRAIGHT-[0, 120], FAR_SCURVE+[0, 50]
    gray = render([(first, 20), (second, 20)])
    state = make_state(gray)
    traced = [editor.trace_tube(state, dict(revision=state['revision'], points=[c[0].tolist(), c[-1].tolist()])) for c in (first, second)]
    assert [t['object_id'] for t in traced] == [1, 2] and len(state['masks']) == 2
    for t in traced:
        annotation = state['annotations'][str(t['object_id'])]
        assert annotation['measurement_methods'] == dict(length='auto_centerline', width='auto_width') and 'tube' in annotation
        assert manual_geometry(annotation)['length_pixels'] == pytest.approx(t['tube']['length_px'], abs=1e-6)
        assert report_geometry(state['masks'][t['object_id']], annotation)['length_pixels'] == pytest.approx(t['tube']['length_px'], abs=1e-6)
    assert measured_overlay(state).size == gray.shape[::-1]
    # Separate T (length) and D (width) figures: every label inside the image, no two labels overlapping.
    from PIL import ImageDraw
    original_text, boxes = ImageDraw.ImageDraw.text, []
    def recording_text(self, xy, text, *args, **kwargs):
        boxes.append((text, self.textbbox(xy, text, font=kwargs.get('font'), stroke_width=kwargs.get('stroke_width', 0))))
        return original_text(self, xy, text, *args, **kwargs)
    ImageDraw.ImageDraw.text = recording_text
    try:
        for show_length, prefix in ((True, 'T'), (False, 'D')):
            boxes.clear()
            figure = measured_overlay(state, show_length=show_length, show_width=not show_length)
            assert [t[0] for t, _ in boxes] == [prefix, prefix]
            for _, (x0, y0, x1, y1) in boxes:
                assert 0 <= x0 and 0 <= y0 and x1 <= figure.width and y1 <= figure.height
            (_, a), (_, b) = boxes
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]
    finally:
        ImageDraw.ImageDraw.text = original_text
    assert all(np.isfinite(row['length_um']) for row in editor.measurements(state)['candidates'])
    with pytest.raises(ValueError, match='^T1 is already measured'):
        editor.trace_tube(state, dict(revision=state['revision'], points=[first[0].tolist(), first[-1].tolist()]))
    with pytest.raises(ValueError, match='inside the image'):
        editor.trace_tube(state, dict(revision=state['revision'], points=[[1, 1]]))
    editor.mutate(state, dict(revision=state['revision']), 'undo')
    assert list(state['masks']) == [1]


def test_measure_tube_on_existing_mask(tmp_path):
    from lab_editor import LabEditor
    editor = LabEditor(output_root=tmp_path/'edits', project_root=tmp_path/'projects', device='cpu')
    gray = render([(SCURVE, 20)])
    mask = np.zeros(gray.shape, np.uint8)
    cv2.polylines(mask, [np.rint(SCURVE).astype(np.int32)], False, 1, 20)
    state = make_state(gray)
    state.update(masks={1: mask.astype(bool)}, annotations={'1': dict(source='prompted_sam')}, next_id=2)
    editor.save(state, dict(state['masks']), dict(state['annotations']), [], 2, dict(type='test'))
    result = editor.measure_tube(state, dict(revision=state['revision'], object_id=1))
    annotation = state['annotations']['1']
    assert annotation['source'] == 'prompted_sam' and annotation['measurement_methods']['length'] == 'auto_centerline'
    assert abs(result['tube']['length_px']/(arc(SCURVE)+20)-1) <= .03
    with pytest.raises(ValueError, match='segmented object'):
        editor.measure_tube(state, dict(revision=state['revision'], object_id=9))


def label_boxes(state, **options):
    """{label text: text box} as drawn by measured_overlay."""
    from PIL import ImageDraw
    from lab_geometry import measured_overlay
    original, boxes = ImageDraw.ImageDraw.text, {}
    def recording(self, xy, text, *args, **kwargs):
        boxes[text] = self.textbbox(xy, text, font=kwargs.get('font'), stroke_width=kwargs.get('stroke_width', 0))
        return original(self, xy, text, *args, **kwargs)
    ImageDraw.ImageDraw.text = recording
    try:
        figure = measured_overlay(state, **options)
    finally:
        ImageDraw.ImageDraw.text = original
    return boxes, figure


def box_distance(box, path):
    x0, y0, x1, y1 = box
    return float(np.min(np.hypot(np.maximum(np.maximum(x0-path[:, 0], path[:, 0]-x1), 0), np.maximum(np.maximum(y0-path[:, 1], path[:, 1]-y1), 0))))


def new_editor(tmp_path):
    from lab_editor import LabEditor
    return LabEditor(output_root=tmp_path/'edits', project_root=tmp_path/'projects', device='cpu')


@pytest.mark.parametrize('half_gap, modes', [(20, ['T']), (30, ['T', 'D', 'TD'])])
def test_labels_sit_beside_their_own_tube(tmp_path, half_gap, modes):
    # two parallel tubes (40 / 60 px apart): every label's nearest line is its own, with a clear margin.
    # Tubes 40 px apart have no clean section (the neighbour is within W), so only T is drawn for them.
    from lab_geometry import tube_width_segments
    editor = new_editor(tmp_path)
    upper, lower = STRAIGHT-[0, half_gap], STRAIGHT+[0, half_gap]
    state = make_state(render([(upper, 20), (lower, 20)]))
    for curve in (upper, lower):
        editor.trace_tube(state, dict(revision=state['revision'], points=[curve[0].tolist(), curve[-1].tolist()]))
    annotation = lambda i, axis: state['annotations'][str(i)]['manual_measurements'][axis]
    lines = {'T': {i: np.asarray(annotation(i, 'length'), float) for i in (1, 2)}, 'D': {}}
    if 'D' in modes:
        lines['D'] = {i: np.vstack([p+(q-p)*np.linspace(0, 1, 50)[:, None] for p, q in tube_width_segments(annotation(i, 'width'))]) for i in (1, 2)}
    for mode in modes:
        boxes, _ = label_boxes(state, show_length='T' in mode, show_width='D' in mode)
        assert len(boxes) == 2*len(mode)
        for text, box in boxes.items():
            kind, own = text[0], int(text[1])
            near = box_distance(box, lines[kind][own])
            far = box_distance(box, np.vstack([lines[k][i] for k in mode for i in (1, 2) if i != own]))
            assert near < far and far >= max(2*near, near+15), (text, near, far)


def test_clean_section_avoids_crossing_fibre():
    fibre = np.column_stack([250+200*T, 150+300*T])   # crosses the tube at its middle (350, 300)
    clean = render([(STRAIGHT, 20)])
    crossed = np.maximum(clean, render([(fibre, 12)], seed=1))
    ends = [STRAIGHT[0].tolist(), STRAIGHT[-1].tolist()]
    reference = trace_tube(clean, ridge_for(clean), ends)['width_px']
    c = trace_tube(crossed, ridge_for(crossed), ends)
    assert c['width_px'] is not None and abs(c['width_px']/reference-1) <= .10
    station = c['width_station']
    mid = (np.asarray(c['width_line'][0])+np.asarray(c['width_line'][1]))/2
    assert station['clean'] and station['quality'] >= .4
    assert np.hypot(*(np.array([350, 300])-mid)) > 25  # the old fixed middle station sat on the crossing


def test_no_clean_section_gives_no_width():
    # crossed by a fibre every ~55 px: no clean section, so D is withheld but the tube still gets a mask band
    fibres = [(np.column_stack([x0+80*T, 150+300*T]), 12) for x0 in range(110, 560, 55)]
    gray = np.maximum(render([(STRAIGHT, 20)]), render(fibres, seed=1))
    c = trace_tube(gray, ridge_for(gray), [STRAIGHT[0].tolist(), STRAIGHT[-1].tolist()])
    assert c['width_px'] is None and c['width_line'] == [] and c['band_px'] > 0


def test_length_only_and_width_only_objects(tmp_path):
    from analyze_candidates import measure_masks
    editor = new_editor(tmp_path)
    upper, lower = STRAIGHT-[0, 100], SCURVE+[0, 150]
    state = make_state(render([(upper, 20), (lower, 20)]))
    revision = lambda: dict(revision=state['revision'])
    length_only = editor.trace_tube(state, dict(revision(), kind='t', points=[upper[0].tolist(), upper[-1].tolist()]))
    width_only = editor.trace_tube(state, dict(revision(), kind='d', points=[[lower[200][0], lower[200][1]+4]]))  # one click, off the centre line
    assert 'length_px' not in length_only  # tube values live under `tube`
    assert length_only['tube']['width'] is None and length_only['tube']['length'] > 0
    assert width_only['tube']['length'] is None and abs(width_only['tube']['width_px']/20-1) <= .25
    a, b = state['annotations']['1'], state['annotations']['2']
    assert set(a['manual_measurements']) == {'length'} and a['measurement_methods'] == dict(length='auto_centerline') and a['tube']['kind'] == 't'
    assert set(b['manual_measurements']) == {'width'} and b['measurement_methods'] == dict(width='auto_width') and b['tube']['kind'] == 'd'
    assert b['tube']['width_station']['quality'] > 0 and state['masks'][2].sum() >= 20
    assert abs(float(np.mean(np.asarray(b['manual_measurements']['width']), axis=0)[1])-lower[200][1]) <= 8  # on the clicked tube
    rows = {r['candidate_id']: r for r in editor.measurements(state)['candidates']}
    assert rows[1]['length_um'] > 0 and rows[1]['width_um'] is None
    assert rows[2]['length_um'] is None and rows[2]['width_um'] > 0
    table = measure_masks(sorted(state['masks'].items()), state['gray'].shape, UMP, gray=state['gray'], manual=state['annotations'])[0]
    lines = table.to_csv(index=False).splitlines()
    header = lines[0].split(',')
    cells = {int(line.split(',')[0]): dict(zip(header, line.split(','))) for line in lines[1:]}
    assert cells[1]['width_um'] == '' and cells[1]['length_um'] != '' and cells[2]['length_um'] == '' and cells[2]['width_um'] != ''
    for options, present, absent in ((dict(show_length=True, show_width=False), ['T1'], ('D', 'T2')), (dict(show_length=False, show_width=True), ['D2'], ('T', 'D1')),
                                     ({}, ['D2', 'T1'], ('D1', 'T2'))):
        boxes, figure = label_boxes(state, **options)
        assert figure.size == state['gray'].shape[::-1]
        assert sorted(t.split('=')[0] for t in boxes) == present and not any(t.startswith(absent) for t in boxes)
    with pytest.raises(ValueError, match='one click'):
        editor.trace_tube(state, dict(revision(), kind='d', points=[[10, 10], [20, 20]]))
    with pytest.raises(ValueError, match='kind'):
        editor.trace_tube(state, dict(revision(), kind='x', points=[[10, 10]]))
    editor.mutate(state, dict(revision=state['revision']), 'undo')
    assert list(state['masks']) == [1] and state['annotations'].keys() == {'1'}


def test_learned_map_constant_still_traces_between_clicks():
    gray = render([(SCURVE, 20)])
    clicks = [SCURVE[0].tolist(), SCURVE[-1].tolist()]
    for value in (1., 0.):
        ridge = dict(ridge_for(gray), P=np.full(gray.shape, value, np.float32))
        c = trace_tube(gray, ridge, clicks)
        assert c['learned'] and np.allclose(c['path'][0], clicks[0]) and np.allclose(c['path'][-1], clicks[-1])
    assert trace_tube(gray, ridge_for(gray), clicks)['learned'] is False


def test_learned_map_picks_the_labelled_strand_at_a_crossing():
    # the crossing fibre is brighter and wider, so the band filter alone has no reason to prefer SCURVE
    gray = np.maximum(render([(SCURVE, 12)]), render([(CROSS, 20)], seed=1)+25)
    mask = np.zeros(gray.shape, np.uint8)
    cv2.polylines(mask, [np.rint(SCURVE).astype(np.int32)], False, 1, 1)
    P = np.exp(-ndi.distance_transform_edt(mask == 0)**2/(2*2.5**2)).astype(np.float32)
    c = trace_tube(gray, dict(ridge_for(gray), P=P), [SCURVE[0].tolist(), SCURVE[-1].tolist()])
    assert np.mean(cKDTree(SCURVE).query(c['path'])[0]) < 3


def test_centerline_map_missing_model_is_none(tmp_path):
    assert centerline_map(np.zeros((64, 64), np.uint8), tmp_path/'absent.xml') is None


def test_centerline_map_shape_and_range():
    from app_paths import ASSET_ROOT
    if not (ASSET_ROOT/cnt_detect.MODEL_FILE).is_file(): pytest.skip('no model file')
    gray = np.random.default_rng(0).integers(0, 255, (946, 1023), dtype=np.uint8)
    P = centerline_map(gray)
    assert P.shape == gray.shape and P.dtype == np.float32 and 0 <= P.min() and P.max() <= 1


def hand_drag(curve, rng, lo=8, hi=392, amp=3., count=100):
    """A freehand-like stroke along a curve: slow sideways wander, mouse jitter, both ends a few px inside the tube."""
    idx = np.linspace(lo, hi, count).astype(int)
    normal = np.gradient(curve, axis=0)[idx][:, ::-1]*[-1, 1]
    normal /= np.linalg.norm(normal, axis=1, keepdims=True)
    return curve[idx]+(amp*np.sin(idx/25.))[:, None]*normal+rng.normal(0, 1, (count, 2))


def test_stroke_stays_in_corridor_where_clicks_take_the_shortcut():
    # a brighter, wider straight tube joins the ends of the S-curve: two clicks take that shortcut, a stroke along the S-curve must not
    from cnt_detect import STROKE_CORRIDOR, STROKE_CORRIDOR_MIN, trace_stroke
    chord = np.column_stack([100+550*T, 300+0*T])
    gray = np.maximum(render([(SCURVE, 14)]), render([(chord, 24)], seed=1)+30)
    ridge = ridge_for(gray)
    clicks = trace_tube(gray, ridge, [SCURVE[0].tolist(), SCURVE[-1].tolist()])
    assert np.max(cKDTree(SCURVE).query(clicks['path'])[0]) > 30   # the click trace is free to leave the S-curve, and does
    stroke = hand_drag(SCURVE, np.random.default_rng(3))
    c = trace_stroke(gray, ridge, stroke)
    assert np.max(cKDTree(stroke).query(c['path'])[0]) <= max(STROKE_CORRIDOR*24, STROKE_CORRIDOR_MIN)+4   # inside the corridor
    d = cKDTree(SCURVE).query(c['path'])[0]
    assert np.mean(d) <= 3 and np.max(d) <= 8
    assert abs(c['length_px']/arc(SCURVE)-1) <= .06 and c['source'] == 'trace'
    assert max(c['end_shift']) <= 14   # one tube width at most
    assert_width(c, 14)


def test_stroke_ends_move_only_a_little():
    from cnt_detect import trace_stroke
    gray = render([(SCURVE, 20)])
    ridge = ridge_for(gray)
    stroke = hand_drag(SCURVE, np.random.default_rng(5), lo=0, hi=399)    # ends on the tube tips, drawn off-centre
    assert max(trace_stroke(gray, ridge, stroke)['end_shift']) <= 20
    # drawn 25 px beyond the tube tip, in the background: the end moves back toward the tube, at most one width
    beyond = np.vstack([[SCURVE[0]-[25, 0]], stroke])
    c = trace_stroke(gray, ridge, beyond)
    assert c['end_shift'][0] <= 20+1e-6 and np.hypot(*(c['path'][0]-SCURVE[0])) < np.hypot(*(beyond[0]-SCURVE[0]))


def test_short_straight_stroke_and_validation():
    from cnt_detect import trace_stroke
    gray = render([(STRAIGHT, 20)])
    ridge = ridge_for(gray)
    c = trace_stroke(gray, ridge, [[300, 302], [330, 299]])
    assert 25 <= c['length_px'] <= 40 and np.max(np.abs(c['path'][:, 1]-300)) <= 4
    c = trace_stroke(gray, ridge, [[300, 300], [301, 300.5], [310, 300], [320, 301], [340, 300]])
    assert abs(c['length_px']-40) <= 8
    for bad in ([[300, 300]], [[1, 2, 3], [4, 5, 6]], [[300, 300], [np.nan, 5]], 'x', [[300, 300]]*5000):
        with pytest.raises(ValueError):
            trace_stroke(gray, ridge, bad)
    for same in ([[300, 300], [300, 300]], [[300, 300], [300.2, 300], [300, 300.3]]):
        with pytest.raises(ValueError, match='at least 2 distinct points'):
            trace_stroke(gray, ridge, same)


def test_stroke_through_the_editor_matches_the_click_response(tmp_path):
    editor = new_editor(tmp_path)
    upper, lower = STRAIGHT-[0, 100], SCURVE+[0, 150]
    state = make_state(render([(upper, 20), (lower, 20)]))
    revision = lambda: dict(revision=state['revision'])
    click = editor.trace_tube(state, dict(revision(), points=[upper[0].tolist(), upper[-1].tolist()]))
    preview = editor.trace_tube(state, dict(revision(), stroke=True, preview=True, kind='td', points=hand_drag(lower, np.random.default_rng(2), count=300).tolist()))
    assert preview['preview'] is True and len(preview['path']) > 10 and len(state['masks']) == 1   # preview saves nothing
    drag = editor.trace_tube(state, dict(revision(), stroke=True, kind='td', points=hand_drag(lower, np.random.default_rng(2), count=300).tolist()))   # > 20 points
    assert set(drag) == set(click) and set(drag['tube']) == set(click['tube']) and drag['object_id'] == 2
    assert abs(drag['tube']['length_px']/arc(lower)-1) <= .06 and drag['tube']['width'] > 0
    assert state['annotations']['2']['tube']['kind'] == 'td' and state['annotations']['2']['source'] == 'cnt_trace'
    for payload in (dict(stroke=True, kind='d', points=[[10, 10], [50, 50]]), dict(stroke=True, points=[[10, 10]]), dict(stroke=True, points=[[10, 10]]*3)):
        with pytest.raises(ValueError):
            editor.trace_tube(state, dict(revision(), **payload))
    assert len(state['masks']) == 2
    only_t = editor.trace_tube(state, dict(revision(), stroke=True, kind='t', points=hand_drag(STRAIGHT-[0, 250], np.random.default_rng(2), lo=10, hi=390).tolist()))
    assert only_t['tube']['width'] is None and only_t['tube']['length'] > 0


def test_box_width_on_existing_tube_replaces_d_and_undo_restores_it(tmp_path):
    editor = new_editor(tmp_path)
    state = make_state(render([(SCURVE, 20)]))
    revision = lambda: dict(revision=state['revision'])
    editor.trace_tube(state, dict(revision(), kind='t', points=[SCURVE[0].tolist(), SCURVE[-1].tolist()]))
    assert state['annotations']['1']['tube']['kind'] == 't' and 'width' not in state['annotations']['1']['manual_measurements']
    masks_before = state['masks'][1].copy()
    def box(i, half=45):
        x, y = SCURVE[i]
        return [x+half, y+half, x-half, y-half]   # corners in the wrong order on purpose
    first = editor.measure_tube(state, dict(revision(), box=box(100)))
    assert first['object_id'] == 1 and first['replaced'] is True and first['tube']['kind'] == 'td'
    assert abs(first['tube']['width_px']/20-1) <= .25 and first['tube']['length'] > 0 and len(state['masks']) == 1
    annotation = state['annotations']['1']
    assert annotation['tube']['kind'] == 'td' and annotation['measurement_methods']['width'] == 'auto_width'
    assert np.hypot(*(np.mean(annotation['manual_measurements']['width'], axis=0)-SCURVE[100])) <= 60   # measured inside the box
    assert np.array_equal(state['masks'][1], masks_before)
    line_a = annotation['manual_measurements']['width']
    second = editor.measure_tube(state, dict(revision(), box=box(300)))   # D replaced elsewhere: no 'already measured'
    line_b = state['annotations']['1']['manual_measurements']['width']
    assert second['object_id'] == 1 and line_b != line_a and np.hypot(*(np.mean(line_b, axis=0)-SCURVE[300])) <= 60
    editor.mutate(state, dict(revision()), 'undo')
    assert state['annotations']['1']['manual_measurements']['width'] == line_a
    editor.mutate(state, dict(revision()), 'undo')
    assert 'width' not in state['annotations']['1']['manual_measurements'] and state['annotations']['1']['tube']['kind'] == 't'


def test_box_width_on_empty_background_makes_a_width_only_object(tmp_path):
    editor = new_editor(tmp_path)
    upper, lower = STRAIGHT-[0, 100], SCURVE+[0, 150]
    state = make_state(render([(upper, 20), (lower, 20)]))
    revision = lambda: dict(revision=state['revision'])
    editor.trace_tube(state, dict(revision(), kind='t', points=[upper[0].tolist(), upper[-1].tolist()]))
    x, y = lower[200]
    result = editor.measure_tube(state, dict(revision(), box=[x-40, y-30, x+40, y+30]))   # on the second tube: no centerline of an object there
    assert result['object_id'] == 2 and result['replaced'] is False and set(result['tube']) == {'kind', 'length_px', 'width_px', 'length', 'width', 'unit', 'clean'}
    assert result['tube']['kind'] == 'd' and result['tube']['length'] is None and abs(result['tube']['width_px']/20-1) <= .25
    b = state['annotations']['2']
    assert b['tube']['kind'] == 'd' and set(b['manual_measurements']) == {'width'} and abs(float(np.mean(b['manual_measurements']['width'], axis=0)[1])-y) <= 30
    assert state['masks'][2].sum() >= 20
    # a box on a D-only mark re-measures that object instead of failing with 'already measured'
    again = editor.measure_tube(state, dict(revision(), box=[x-40, y-30, x+40, y+30]))
    assert again['object_id'] == 2 and again['replaced'] is True and len(state['masks']) == 2
    with pytest.raises(ValueError, match='No tube found in this box'):
        editor.measure_tube(state, dict(revision(), box=[700, 520, 780, 580]))
    for box in ([1, 2, 3], [1, 2, 3, np.nan], 'abc', [10, 10, 11, 200], [-50, -50, -40, -40]):
        with pytest.raises(ValueError, match='box'):
            editor.measure_tube(state, dict(revision(), box=box))
    editor.mutate(state, dict(revision()), 'undo')
    editor.mutate(state, dict(revision()), 'undo')
    assert list(state['masks']) == [1]


def tube_strips(strips, shape=(300, 420)):
    """Report state with one measured tube per strip (x0, x1, y0, y1, mark): a vertical band, its centre line (T) and a D mark across it at y = mark.
    A 6th item 'h' makes the tube horizontal (mark = x)."""
    state = make_state(np.full(shape, 90, np.uint8))
    for i, (x0, x1, y0, y1, mark, *horizontal) in enumerate(strips, 1):
        mask = np.zeros(shape, bool)
        mask[y0:y1, x0:x1] = True
        state['masks'][i] = mask
        across, along = ([[mark, y0], [mark, y1]], [[x0, (y0+y1)/2], [x1, (y0+y1)/2]]) if horizontal else ([[x0, mark], [x1, mark]], [[(x0+x1)/2, y0], [(x0+x1)/2, y1]])
        state['annotations'][str(i)] = dict(source='cnt_trace', supplemental=True, tube=dict(kind='td'), manual_measurements=dict(length=along, width=across),
                                            measurement_methods=dict(length='auto_centerline', width='auto_width'))
    state['next_id'] = len(strips)+1
    return state


LABEL_CASES = {
    'three adjacent tubes, D marks 3 px apart': [(88, 108, 40, 160, 100), (112, 132, 40, 160, 103), (136, 156, 40, 160, 106)],
    'two D marks 2 px apart': [(88, 108, 40, 160, 100), (111, 131, 40, 160, 102)],
    'D marks on one row': [(88, 108, 40, 160, 100), (112, 132, 40, 160, 100), (136, 156, 40, 160, 100), (160, 180, 40, 160, 100)],
    'marks at the image border': [(0, 20, 40, 160, 100), (400, 420, 40, 160, 120), (200, 220, 0, 20, 100, 'h'), (260, 280, 280, 300, 100, 'h'), (0, 20, 200, 220, 1, 'h')],
    'ten tubes 5 px apart': [(20+25*i, 40+25*i, 100, 200, 130+(i % 3)*3) for i in range(10)],
}


@pytest.mark.parametrize('name', LABEL_CASES)
def test_tube_labels_never_overlap_stay_inside_and_stay_attached(name):
    from PIL import ImageDraw
    from lab_geometry import TUBE_COLOR, measured_overlay, tube_width_segments
    state = tube_strips(LABEL_CASES[name])
    original_text, original_line = ImageDraw.ImageDraw.text, ImageDraw.ImageDraw.line
    boxes, lines = {}, []
    def text(self, xy, string, *args, **kwargs):
        boxes[string] = self.textbbox(xy, string, font=kwargs.get('font'), stroke_width=kwargs.get('stroke_width', 0))
        return original_text(self, xy, string, *args, **kwargs)
    def line(self, xy, *args, **kwargs):
        lines.append(np.asarray(xy, float).reshape(-1, 2))
        return original_line(self, xy, *args, **kwargs)
    marks = {}
    for i, annotation in ((i, state['annotations'][str(i)]['manual_measurements']) for i in state['masks']):
        marks[f'D{i}'] = np.vstack([p+(q-p)*np.linspace(0, 1, 60)[:, None] for p, q in tube_width_segments(annotation['width'])])
        marks[f'T{i}'] = np.asarray(annotation['length'], float)[0]+(np.asarray(annotation['length'], float)[1]-np.asarray(annotation['length'], float)[0])*np.linspace(0, 1, 60)[:, None]
    ImageDraw.ImageDraw.text, ImageDraw.ImageDraw.line = text, line
    try:
        for show_length, show_width in ((False, True), (True, False), (True, True)):
            boxes.clear(); lines.clear()
            figure = measured_overlay(state, show_length=show_length, show_width=show_width)
            assert len(boxes) == len(state['masks'])*(show_length+show_width)
            texts = sorted(boxes.items())
            for i, (string, (x0, y0, x1, y1)) in enumerate(texts):
                assert 0 <= x0 and 0 <= y0 and x1 <= figure.width and y1 <= figure.height, string   # not cut by the border
                for other, p in texts[i+1:]:
                    assert p[2] <= x0 or x1 <= p[0] or p[3] <= y0 or y1 <= p[1], (string, other)   # no label over another
                key = string.split('=')[0]
                near = box_distance((x0, y0, x1, y1), marks[key])
                foreign = [m for k, m in marks.items() if k[1:] != key[1:] and k[0] in 'TD'[:0]+('T' if show_length else '')+('D' if show_width else '')]
                far = min(box_distance((x0, y0, x1, y1), m) for m in foreign) if foreign else 1e9
                if far >= max(2*near, near+15)-3: continue   # clearly closer (the placement measures on 1-px rasters: 3 px slack) to its own mark than to any other tube's
                own = marks[key]
                assert any(box_distance((x0, y0, x1, y1), s[:1]) <= 4 and np.min(np.linalg.norm(own-s[1], axis=1)) <= 2.5 for s in lines if len(s) == 2), string
    finally:
        ImageDraw.ImageDraw.text, ImageDraw.ImageDraw.line = original_text, original_line


def test_manual_line_is_saved_exactly_as_clicked(tmp_path):
    editor = new_editor(tmp_path)
    state = make_state(render([(STRAIGHT-[0, 100], 20)]))
    clicks = [[120., 200.], [120., 200.], [350., 203.], [580., 200.]]   # a repeated click is dropped
    result = editor.trace_tube(state, dict(revision=state['revision'], manual=True, kind='td', points=clicks))
    saved = state['annotations'][str(result['object_id'])]
    assert np.allclose(saved['manual_measurements']['length'], [clicks[0], clicks[2], clicks[3]])   # vertices untouched
    assert saved['source'] == 'cnt_manual'
    assert len(saved['manual_measurements']['width']) == 2   # D measured along the drawn line
    with pytest.raises(ValueError):
        editor.trace_tube(state, dict(revision=state['revision'], manual=True, kind='d', points=clicks))
    with pytest.raises(ValueError):
        editor.trace_tube(state, dict(revision=state['revision'], manual=True, kind='t', points=[[10, 10]]))


def test_width_from_two_parallel_lines(tmp_path):
    editor = new_editor(tmp_path)
    upper, lower = STRAIGHT-[0, 100], STRAIGHT+[0, 150]
    state = make_state(render([(upper, 20), (lower, 20)]))
    revision = lambda: dict(revision=state['revision'])
    tube = editor.trace_tube(state, dict(revision(), kind='t', points=[upper[0].tolist(), upper[-1].tolist()]))
    # one edge of the upper tube, then a click on the other edge: D on that tube, as the distance between the lines
    on_tube = editor.measure_tube(state, dict(revision(), edge=[[250, 190], [330, 190]], point=[290, 212]))
    assert on_tube['replaced'] and on_tube['object_id'] == tube['object_id'] and on_tube['tube']['kind'] == 'td'
    assert abs(on_tube['tube']['width_px']-22) < 1e-6
    annotation = state['annotations'][str(tube['object_id'])]
    assert annotation['width_edges'] == [[[250, 190], [330, 190]], [[250, 212], [330, 212]]] and annotation['measurement_methods']['width'] == 'manual_width'
    # nothing measured under the lines: a new width-only object
    alone = editor.measure_tube(state, dict(revision(), edge=[[250, 440], [330, 440]], point=[300, 461]))
    assert not alone['replaced'] and alone['tube']['kind'] == 'd' and abs(alone['tube']['width_px']-21) < 1e-6
    from lab_geometry import measured_overlay
    assert measured_overlay(state, show_length=False).size == state['gray'].shape[::-1]
    for bad in (dict(edge=[[250, 440], [251, 440]], point=[300, 461]), dict(edge=[[250, 440], [330, 440]], point=[300, 440.5])):
        with pytest.raises(ValueError):
            editor.measure_tube(state, dict(revision(), **bad))


def test_save_labels_beside_the_original(tmp_path, monkeypatch):
    from PIL import Image
    editor = new_editor(tmp_path)
    gray = render([(STRAIGHT, 20)])
    state = make_state(gray)
    folder = tmp_path/'images'; folder.mkdir()
    source = folder/'CNT_x-1.tif'; Image.fromarray(gray.astype(np.uint8)).save(source)
    full = tmp_path/'display.png'; Image.fromarray(np.zeros((gray.shape[0]+40, gray.shape[1], 3), np.uint8)).save(full)   # + info bar
    state['report']['rgb_image'] = str(full)
    assert editor.save_labels(state, {}) == dict(no_tubes=True)
    editor.trace_tube(state, dict(revision=state['revision'], points=[STRAIGHT[0].tolist(), STRAIGHT[-1].tolist()]))
    monkeypatch.setattr(editor, 'source_path', lambda s: None)
    assert editor.save_labels(state, {}) == dict(need_folder=True)
    monkeypatch.setattr(editor, 'source_path', lambda s: source)
    saved = editor.save_labels(state, {})
    assert [Path(p).name for p in saved['saved']] == ['CNT_x-1(2).tif', 'CNT_x-1(3).tif', 'CNT_x-1(2).csv', 'CNT_x-1(3).csv']
    lengths, widths = ((folder/n).read_text(encoding='utf-8-sig').splitlines() for n in ('CNT_x-1(2).csv', 'CNT_x-1(3).csv'))
    assert lengths[0] == 'label,length_µm' and lengths[1].startswith('T1,') and widths[0] == 'label,width_µm' and widths[1].startswith('D1,')
    two, three = (np.asarray(Image.open(p).convert('RGB')) for p in saved['saved'][:2])
    assert two.shape == (gray.shape[0]+40, gray.shape[1], 3)   # whole image, info bar included
    yellow = lambda a: ((a[..., 0] > 200) & (a[..., 1] > 200) & (a[..., 2] < 80)).sum()
    assert yellow(two) > 0 and yellow(three) > 0 and not np.array_equal(two, three)
    assert editor.save_labels(state, {})['exists'] == ['CNT_x-1(2).tif', 'CNT_x-1(3).tif', 'CNT_x-1(2).csv', 'CNT_x-1(3).csv']   # never replaced without asking
    assert len(editor.save_labels(state, dict(overwrite=True))['saved']) == 4
