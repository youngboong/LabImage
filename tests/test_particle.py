import csv
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import cv2
import numpy as np
import pytest
from particle_detect import REF_UM_PER_PX, detect_particles, exclusion_reason, feret_measure, particle_features

ROOT = Path(__file__).resolve().parents[1]
UMP = REF_UM_PER_PX


def ellipse(shape, c, axes, angle=0):
    m = np.zeros(shape, np.uint8)
    cv2.ellipse(m, tuple(int(v) for v in c), tuple(int(v) for v in axes), angle, 0, 360, 1, -1)
    return m.astype(bool)


def polygon(shape, pts):
    m = np.zeros(shape, np.uint8)
    cv2.fillPoly(m, [np.rint(pts).astype(np.int32)], 1)
    return m.astype(bool)


def scene(shape, masks, level=80, base=60):
    gray = np.full(shape, base, np.uint8)
    for m in masks: gray[m] = level
    return gray


def min_extent(mask):
    """Narrowest projection extent of the pixel cells over 0.5 degree steps (brute force)."""
    yy, xx = np.nonzero(mask); p = (np.stack([xx, yy], 1)[:, None, :]+np.array([[-.5, -.5], [-.5, .5], [.5, -.5], [.5, .5]])[None]).reshape(-1, 2)
    th = np.radians(np.arange(0, 180, .5)); return float(np.ptp(p@np.stack([np.cos(th), np.sin(th)]), axis=0).min())


@pytest.mark.parametrize('angle', [0, 30, 75])
def test_ellipse_length_and_widths(angle):
    m = ellipse((300, 300), (150, 150), (80, 35), angle)
    f = feret_measure(m)
    assert f['length_px'] == pytest.approx(161, abs=2.5)   # pixel extent of the raster: 2a+1
    assert f['width_px'] == pytest.approx(71, abs=3)
    assert f['width_caliper_px'] == pytest.approx(71, abs=3)
    assert f['solidity'] > .95
    a, b = np.array(f['length_line']), np.array(f['width_line'])
    assert np.linalg.norm(b[1]-b[0]) == pytest.approx(f['width_px'], abs=1e-6)
    assert f['width_px'] <= min_extent(m)+1e-6   # no direction is narrower: this is the minimum Feret


def test_rotated_rectangle_width_is_the_minimum_feret():
    c, th = np.array([150., 150.]), np.radians(30)
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    m = polygon((300, 300), c+np.array([[-50, -20], [50, -20], [50, 20], [-50, 20]])@R.T)
    f = feret_measure(m)
    assert f['length_px'] == pytest.approx(np.hypot(100, 40), abs=1.5)   # the diagonal
    assert f['width_px'] == pytest.approx(41, abs=1.5)                   # the short side, not the 74 px extent perpendicular to the diagonal
    assert f['width_caliper_px'] == f['width_px'] and f['width_chord_px'] == pytest.approx(43.1, abs=1.5)   # the mid-chord is kept for the standing rule
    a, b = np.array(f['length_line']), np.array(f['width_line'])
    assert np.linalg.norm(b[1]-b[0]) == pytest.approx(f['width_px'], abs=1e-6)
    u = (b[1]-b[0])/f['width_px']; assert abs(abs(u@R[:, 1])-1) < .02   # the width line runs along the short side


def test_notched_shape_width_spans_the_notch():
    m = np.zeros((200, 200), bool); m[50:150, 40:60] = True; m[50:150, 100:120] = True; m[130:150, 40:120] = True   # U: two arms joined at the bottom
    m[50:90, 60:100] = False
    f = feret_measure(m)
    assert f['width_px'] == pytest.approx(80, abs=1e-6) and f['width_px'] <= min_extent(m)+1e-6   # outer width of the U: the notch does not shorten it
    line = np.array(f['width_line']); assert np.linalg.norm(line[1]-line[0]) == pytest.approx(f['width_px'], abs=1e-6)
    one = np.zeros((50, 50), bool); one[20, 10:40] = True
    assert 1 <= feret_measure(one)['width_px'] < 2.1   # a 1-px line is a cell or two wide (the diagonal tilts the normal), not 0


def test_l_shape_has_low_solidity():
    m = np.zeros((200, 200), bool); m[20:120, 20:40] = True; m[100:120, 20:120] = True
    assert feret_measure(m)['solidity'] < .8


def test_cut_off_overlapped_and_kept():
    shape = (300, 300)
    low = ellipse(shape, (150, 150), (50, 30))             # kept
    edge = ellipse(shape, (200, 299), (40, 30))            # touches the bottom row
    gray = scene(shape, [low, edge], level=80)
    kept, counts = detect_particles(gray, [low, edge], UMP)
    assert len(kept) == 1 and kept[0]['mask'] is low and counts['cut_off'] == 1 and sum(counts.values()) == 1
    left, right = np.zeros(shape, bool), np.zeros(shape, bool)
    left[100:160, 100:140] = True; right[100:160, 140:180] = True   # share one 60 px side of a ~200 px outline
    rows = particle_features([left, right], scene(shape, [left, right], level=80), UMP)
    assert all(.2 < r['contact'] < .5 and exclusion_reason(r) == 'overlapped' for r in rows)


def test_thresholds_follow_the_scale():
    disc = ellipse((300, 300), (150, 150), (13, 13))      # ~530 px: below 600 px at 300x
    gray = scene((300, 300), [disc])
    assert detect_particles(gray, [disc], UMP)[1]['small'] == 1
    assert len(detect_particles(gray, [disc], 2*UMP)[0]) == 1   # at 2x um/px the limit is 150 px
    assert not particle_features([ellipse((300, 300), (150, 150), (14, 14))], gray, UMP)[0]['small']   # ~615 px


def test_standing_by_aspect_and_not_particle():
    shape = (300, 300)
    long_ = polygon(shape, [[40, 140], [260, 140], [260, 160], [40, 160]])
    assert exclusion_reason(particle_features([long_], scene(shape, [long_]), UMP)[0]) == 'standing'
    faint = ellipse(shape, (150, 150), (50, 30))
    assert exclusion_reason(particle_features([faint], scene(shape, [faint], level=63), UMP)[0]) == 'not_particle'


def test_gt_regression_300x_3_p2():
    cache = ROOT/'validation/particle-proto/cache/SWCNT_704113_300x_3_sam16.npz'
    image = ROOT/'261110_704113_powder/SWCNT_704113_300x_3.tif'
    if not (cache.is_file() and image.is_file()): pytest.skip('labelled test image not available')
    from PIL import Image
    gray = np.asarray(Image.open(image).convert('L'))[:768]
    masks = list(np.load(cache)['masks'])
    centre = (417+709)//2, (496+440)//2   # midpoint of the hand-drawn length line, particle 2
    mask = next(m for m in masks if m[centre[1], centre[0]])
    f = feret_measure(mask)
    assert f['length_px'] == pytest.approx(297.1, rel=.03) and f['width_px'] == pytest.approx(189.6, rel=.04)
    assert any(k['mask'] is mask for k in detect_particles(gray, masks, UMP)[0])


# ---- editor level, SAM replaced by fixed masks ----
SHAPE = (300, 400)
A, B, C = ellipse(SHAPE, (100, 80), (60, 25)), ellipse(SHAPE, (280, 100), (50, 30), 40), ellipse(SHAPE, (200, 299), (40, 30))
SPECK = ellipse(SHAPE, (30, 250), (5, 5))


@pytest.fixture
def lab(tmp_path, monkeypatch):
    from lab_editor import LabEditor
    editor = LabEditor(output_root=tmp_path/'edits', project_root=tmp_path/'projects', device='cpu')
    gray = scene(SHAPE, [A, B, C, SPECK])
    state = dict(dataset='t', gray=gray, rgb=np.repeat(gray[:, :, None], 3, axis=2),
        report=dict(workspace_mode='report', image='x.png', source_name='img.png', scale=dict(um_per_pixel=UMP), measurement_unit='µm'),
        masks={}, annotations={}, history=[], next_id=1, revision=0)
    monkeypatch.setattr(LabEditor, 'automatic_masks', lambda self, s: [A, B, C, SPECK])
    monkeypatch.setattr(LabEditor, 'point_masks', lambda self, s, p: [next(m for m in (A, B, C, SPECK) if m[p[1], p[0]])])
    return editor, state


def rev(state): return dict(revision=state['revision'])


def test_detect_is_one_revision_and_one_undo(lab):
    editor, state = lab
    existing = ellipse(SHAPE, (340, 230), (20, 20))   # an object saved earlier stays
    editor.save(state, {1: existing}, {'1': dict(source='prompted_sam')}, [], 2, dict(type='test'))
    r = editor.detect_particles(state, rev(state))
    assert r['object_ids'] == [2, 3] and r['revision'] == 2 and len(state['history']) == 1
    assert r['excluded'] == dict(cut_off=1, overlapped=0, overlapped_shape=0, standing=0, not_particle=0, small=1)
    rows = {x['candidate_id']: x for x in editor.measurements(state)['candidates']}
    assert [rows[i]['particle'] for i in (1, 2, 3)] == [False, True, True] and all(rows[i]['particle_source'] == 'auto' for i in (2, 3))
    assert rows[2]['length_um'] == pytest.approx(121*UMP, abs=1.5*UMP) and rows[2]['width_um'] == pytest.approx(51*UMP, abs=2*UMP)
    with pytest.raises(ValueError, match='^No measurable particle found. Click a particle or draw the lines by hand.$'):
        editor.detect_particles(state, rev(state))   # everything is already measured
    editor.mutate(state, rev(state), 'undo')
    assert list(state['masks']) == [1]


def test_click_adds_one_and_refuses_the_same_particle(lab):
    editor, state = lab
    r = editor.measure_particle(state, dict(rev(state), point=[100, 80]))
    assert r['object_id'] == 1 and r['warning'] is None and r['revision'] == 1
    assert r['particle']['length_px'] == pytest.approx(121, abs=1.5) and r['particle']['unit'] == 'µm'
    assert editor.measurements(state)['candidates'][0]['particle_source'] == 'click'
    assert r['particle']['length'] == pytest.approx(r['particle']['length_px']*UMP)
    with pytest.raises(ValueError, match=r'^This particle is already measured as #1\.$'):
        editor.measure_particle(state, dict(rev(state), point=[110, 85]))
    assert editor.measure_particle(state, dict(rev(state), point=[200, 295]))['warning'] == 'cut_off'   # rules are only a warning on a click
    assert len(state['masks']) == 2 and len(state['history']) == 2


def test_particle_line_creates_then_attaches(lab):
    editor, state = lab
    first = editor.particle_line(state, dict(rev(state), axis='length', points=[[20, 200], [120, 200]]))
    assert first['created'] and first['object_id'] == 1 and first['particle']['width'] is None
    assert first['particle']['length_px'] == pytest.approx(100)
    second = editor.particle_line(state, dict(rev(state), axis='width', points=[[70, 180], [70, 215]]))   # midpoint off the band, crosses the length line
    assert not second['created'] and second['object_id'] == 1 and len(state['masks']) == 1
    a = state['annotations']['1']
    assert a['measurement_methods'] == dict(length='manual_line', width='manual_line') and set(a['manual_measurements']) == {'length', 'width'}
    row = editor.measurements(state)['candidates'][0]
    assert row['particle'] and row['particle_source'] == 'manual' and row['length_um'] == pytest.approx(100*UMP) and row['width_um'] == pytest.approx(35*UMP)
    inside = editor.particle_line(state, dict(rev(state), axis='length', points=[[250, 200], [250, 260]]))
    assert inside['created'] and inside['object_id'] == 2   # touches neither the mask midpoint nor a width line
    explicit = editor.particle_line(state, dict(rev(state), axis='width', points=[[60, 190], [60, 205]], object_id=1))
    assert explicit['particle']['width_px'] == pytest.approx(15) and not explicit['created']
    for bad, message in ((dict(axis='x', points=[[1, 1], [2, 2]]), 'Choose L or W'), (dict(axis='length', points=[[5, 5], [5, 5]]), 'distinct'),
                         (dict(axis='length', points=[[5, 5], [500, 5]]), 'inside the image'), (dict(axis='length', points=[[5, 5]]), 'two points'),
                         (dict(axis='length', points=[[5, 5], [9, 9]], object_id=77), 'measured particle')):
        with pytest.raises(ValueError, match=message): editor.particle_line(state, dict(rev(state), **bad))


def test_line_through_a_detected_particle_attaches_to_it(lab):
    editor, state = lab
    editor.detect_particles(state, rev(state))
    r = editor.particle_line(state, dict(rev(state), axis='width', points=[[100, 50], [100, 110]]))
    assert not r['created'] and r['object_id'] == 1 and r['particle']['width_px'] == pytest.approx(60)
    assert state['annotations']['1']['measurement_methods'] == dict(length='auto_feret', width='manual_line')


def test_save_labels_particle_only(lab, tmp_path):
    editor, state = lab
    editor.detect_particles(state, rev(state))
    out = tmp_path/'out'; out.mkdir()
    r = editor.save_labels(state, dict(directory=str(out)))
    names = ('img(1).png', 'img(2).png', 'img(1).csv', 'img(2).csv')
    assert sorted(Path(p).name for p in r['saved']) == sorted(names) and all((out/n).is_file() for n in names) and not (out/'img(3).png').exists()
    for name in ('(1)', '(2)'):
        table = out/f'img{name}.csv'
        rows = list(csv.reader(open(table, encoding='utf-8-sig')))
        assert rows[0][0] == 'label' and [x[0] for x in rows[1:]] == ['1', '2']
    editor.particle_width_mode(state, dict(rev(state), mode='perpendicular'))
    old = [r['width_um'] for r in editor.measurements(state)['candidates'] if r.get('particle')]
    editor.save_labels(state, dict(directory=str(out)))
    low = [float(x[1]) for x in list(csv.reader(open(out/'img(1).csv', encoding='utf-8-sig')))[1:]]
    assert len(low) == 2 and all(a <= b+.01 for a, b in zip(low, old))   # (1) is the minimum Feret even while the toggle shows Perpendicular
    assert editor.measurements(state)['particle_width_mode'] == 'perpendicular'   # saving does not change the analysis


def test_overlay_labels_are_value_only_and_clear(lab):
    from PIL import ImageDraw
    from lab_geometry import measured_overlay, particle_segments, raster_segments
    editor, state = lab
    editor.detect_particles(state, rev(state))
    original, boxes = ImageDraw.ImageDraw.text, []
    def recording(self, xy, text, *args, **kwargs):
        boxes.append((text, self.textbbox(xy, text, font=kwargs.get('font'))))
        return original(self, xy, text, *args, **kwargs)
    ImageDraw.ImageDraw.text = recording
    try: figure = measured_overlay(state)
    finally: ImageDraw.ImageDraw.text = original
    assert len(boxes) == 4 and all(t.endswith(' µm') and t.split()[0].replace('.', '').isdigit() for t, _ in boxes)
    union = np.zeros(SHAPE, bool)
    for m in state['masks'].values(): union |= m
    lines = np.zeros(SHAPE, bool)
    for a in state['annotations'].values():
        for axis in ('length_line', 'width_line'): lines |= raster_segments(particle_segments(a['particle'][axis], touch=a['particle']['width_touch'] if axis == 'width_line' else None), SHAPE)
    for _, (x0, y0, x1, y1) in boxes:
        assert 0 <= x0 and 0 <= y0 and x1 <= figure.width and y1 <= figure.height
        assert not union[y0:y1, x0:x1].any() and not lines[y0:y1, x0:x1].any()
    for (_, a), (_, b) in ((boxes[i], boxes[j]) for i in range(4) for j in range(i)):
        assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]
    far = union & ~cv2.dilate(lines.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    assert (np.asarray(figure)[far] == state['rgb'][far]).all()   # no mask fill


def test_remove_axis_line_one_revision_and_one_axis_everywhere(lab, tmp_path):
    editor, state = lab
    editor.detect_particles(state, rev(state))
    before = state['revision']
    r = editor.particle_line(state, dict(rev(state), axis='width', points=None, object_id=1))
    assert r['object_id'] == 1 and r['created'] is False and r['revision'] == before+1 and r['particle']['width'] is None
    assert r['particle']['length'] == pytest.approx(r['particle']['length_px']*UMP) and r['particle']['width_px'] is None
    a = state['annotations']['1']
    assert set(a['manual_measurements']) == {'length'} and set(a['measurement_methods']) == {'length'}
    assert a['particle']['width_line'] is None and a['particle']['width_px'] is None and 1 in state['masks']
    row = {x['candidate_id']: x for x in editor.measurements(state)['candidates']}[1]
    assert row['width_um'] is None and row['width_line'] is None and row['length_line'] == a['particle']['length_line'] and row['length_um'] > 0
    for bad, message in ((dict(axis='width', object_id=1), 'no width line'), (dict(axis='length', object_id=77), 'measured particle'), (dict(axis='length'), 'measured particle')):
        with pytest.raises(ValueError, match=message): editor.particle_line(state, dict(rev(state), points=None, **bad))
    out = tmp_path/'out'; out.mkdir()   # figures and CSVs cope with the missing axis
    editor.save_labels(state, dict(directory=str(out)))
    assert [x[0] for x in list(csv.reader(open(out/'img(1).csv', encoding='utf-8-sig')))[1:]] == ['2']
    assert [x[0] for x in list(csv.reader(open(out/'img(2).csv', encoding='utf-8-sig')))[1:]] == ['1', '2']
    editor.particle_line(state, dict(rev(state), axis='width', points=[[100, 50], [100, 110]]))   # redraw after removal attaches again
    assert state['annotations']['1']['particle']['width_px'] == pytest.approx(60)
    editor.mutate(state, rev(state), 'undo'); editor.mutate(state, rev(state), 'undo')
    assert state['annotations']['1']['particle']['width_px'] is not None   # the removal was one undo step
    editor.save(state, {**state['masks'], 9: ellipse(SHAPE, (340, 230), (20, 20))}, {**state['annotations'], '9': dict(source='prompted_sam')}, list(state['history']), 10, dict(type='test'))
    with pytest.raises(ValueError, match='measured particle'): editor.particle_line(state, dict(rev(state), axis='length', points=None, object_id=9))


def test_row_line_geometry_and_warning(lab):
    editor, state = lab
    editor.detect_particles(state, rev(state))
    editor.measure_particle(state, dict(rev(state), point=[200, 295]))   # cut off: a click keeps it with a warning
    editor.particle_line(state, dict(rev(state), axis='length', points=[[20, 200], [120, 200]]))
    rows = {x['candidate_id']: x for x in editor.measurements(state)['candidates']}
    assert rows[1]['particle_warning'] is None and rows[3]['particle_warning'] == 'cut_off' and rows[4]['particle_warning'] is None
    for i in (1, 2, 3):
        p = state['annotations'][str(i)]['particle']
        assert rows[i]['length_line'] == p['length_line'] and rows[i]['width_line'] == p['width_line'] and np.array(rows[i]['length_line']).shape == (2, 2)
    assert rows[4]['length_line'] == [[20, 200], [120, 200]] and rows[4]['width_line'] is None
    state['masks'][9] = ellipse(SHAPE, (340, 230), (20, 20)); state['annotations']['9'] = dict(source='prompted_sam')   # a non-particle row has no lines
    state.pop('measurements', None)
    row = {x['candidate_id']: x for x in editor.measurements(state)['candidates']}[9]
    assert row['length_line'] is None and row['width_line'] is None and row['particle_warning'] is None


def test_particle_report_content_has_length_and_width_tables(lab):
    import report_composer as composer
    editor, state = lab
    editor.detect_particles(state, rev(state))
    editor.particle_line(state, dict(rev(state), axis='width', points=None, object_id=1))   # one particle with only a length
    data = composer.content(editor, state)
    ids = [a['id'] for a in data['assets']]
    assert 'particle_length' in ids and 'particle_width' in ids and 'segmentation' not in ids and {'hist_length', 'hist_width'} <= set(ids) and 'hist_diameter' not in ids
    table = next(a for a in data['assets'] if a['id'] == 'particle_table')
    assert table['headers'] == ['Particle', 'Length (µm)', 'Width (µm)'] and [r[0] for r in table['rows']] == ['1', '2', 'Mean', 'Standard deviation']
    lengths = [r['length_um'] for r in editor.measurements(state)['candidates']]
    assert float(table['rows'][2][1]) == pytest.approx(np.mean(lengths), abs=1e-3) and float(table['rows'][3][1]) == pytest.approx(np.std(lengths, ddof=1), abs=1e-3)
    assert table['rows'][0][2] == '—' and float(table['rows'][2][2]) == pytest.approx(editor.measurements(state)['candidates'][1]['width_um'], abs=1e-3)   # one width: its mean, no SD
    assert table['rows'][3][2] == '—' and 'pore' not in (data['summary']+str(table)).lower() and '2 particles' in data['summary']
    options = composer.defaults(data)
    options['items'] = [dict(id='figure_a', selected=True, caption='L', image_ids=['particle_length'], rows=[['particle_length']], columns=1), dict(id='particle_table', selected=True, caption='T')]
    assert '<table' in composer.render_html(data, composer.validate(options, data))


def test_width_end_lines_touch_the_particle_and_match():
    from lab_geometry import particle_segments
    mask = np.zeros((200, 300), bool)
    cv2.fillPoly(mask.view(np.uint8), [np.array([[40, 100], [150, 60], [260, 110], [120, 150]], np.int32)], 1)   # widest points at different places along the length
    f = feret_measure(mask)
    line, first, second = particle_segments(f['width_line'], touch=f['width_touch'])
    lengths = [float(np.linalg.norm(q-p)) for p, q in (first, second)]
    assert abs(lengths[0]-lengths[1]) < 1e-6 and lengths[0] >= 9-1e-6   # equal and long enough to reach
    direction = lambda p, q: (q-p)/np.linalg.norm(q-p)
    assert abs(abs(direction(*first)@direction(*second))-1) < 1e-9   # parallel
    for (p, q), t in zip((first, second), np.asarray(f['width_touch'])):
        d = direction(p, q); foot = p+((t-p)@d)*d
        assert np.linalg.norm(t-foot) < 1.5 and -1e-6 <= (t-p)@d <= np.linalg.norm(q-p)+1e-6   # the touch point lies on the end line
    assert len(particle_segments(f['width_line'], touch=[[0, 0], [5, 5]])) == 3   # foreign touch points are ignored


def test_batch_lists_only_originals_and_refuses_bad_folders(tmp_path, monkeypatch):
    from lab_editor import LabEditor
    editor = LabEditor(output_root=tmp_path/'edits', project_root=tmp_path/'projects', device='cpu')
    folder = tmp_path/'images'; folder.mkdir()
    for name in ('a.tif', 'a(1).tif', 'a(2).tif', 'b.png', 'b(2).png', 'b(3).png', 'c.png', 'notes.txt'): (folder/name).write_bytes(b'x')
    seen = []
    monkeypatch.setattr(editor, 'batch_one', lambda path, overwrite: seen.append(path.name) or dict(status='saved', particles=1, excluded=0, unit='µm'))
    editor.batch_start(dict(directory=str(folder)))
    for _ in range(100):
        if not editor.batch_status()['running']: break
        import time; time.sleep(.02)
    status = editor.batch_status()
    assert seen == ['b.png', 'c.png'] and status['total'] == 3 and not status['running']   # a has (1) and (2): skipped. b has no (1): made again. c: new
    assert [(r['name'], r['status']) for r in status['results']] == [('a.tif', 'skipped'), ('b.png', 'saved'), ('c.png', 'saved')]
    for bad in (dict(directory=str(tmp_path/'missing')), dict(directory='relative'), {}, dict(directory=str(folder), scale_factor=0), dict(directory=str(folder), scale_factor='2')):
        with pytest.raises(ValueError): editor.batch_start(bad)
    assert status['scale_factor'] == 1. and status['last_scale_factor'] == 1.   # default: the last factor used (none yet)
    editor.batch_start(dict(directory=str(folder), scale_factor=1.25))
    assert editor.batch_status()['scale_factor'] == 1.25


def test_width_mode_switches_between_minimum_and_perpendicular():
    c, th = np.array([150., 150.]), np.radians(30)
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    m = polygon((300, 300), c+np.array([[-50, -20], [50, -20], [50, 20], [-50, 20]])@R.T)
    low, old = feret_measure(m), feret_measure(m, 'perpendicular')
    assert low['width_px'] == pytest.approx(41, abs=1.5) and old['width_px'] == pytest.approx(74.3, abs=1.5)   # short side / extent perpendicular to the diagonal
    assert low['length_line'] == old['length_line'] and low['width_chord_px'] == old['width_chord_px']   # only the width line differs
    a, b = np.array(old['length_line']), np.array(old['width_line'])
    assert abs((a[1]-a[0])@(b[1]-b[0]))/(old['length_px']*old['width_px']) < 1e-6


def test_width_mode_changes_automatic_lines_only_and_is_one_undo(lab):
    editor, state = lab
    editor.detect_particles(state, rev(state))
    editor.particle_line(state, dict(rev(state), axis='width', points=[[100, 50], [100, 110]]))   # particle 1: hand-drawn width
    assert editor.measurements(state)['particle_width_mode'] == 'min'
    before = {i: state['annotations'][str(i)]['particle']['width_px'] for i in (1, 2)}
    r = editor.particle_width_mode(state, dict(rev(state), mode='perpendicular'))
    assert r['object_ids'] == [2] and editor.measurements(state)['particle_width_mode'] == 'perpendicular'
    a = state['annotations']
    assert a['1']['measurement_methods']['width'] == 'manual_line' and a['1']['particle']['width_px'] == before[1]
    assert a['2']['measurement_methods']['width'] == 'auto_feret_perpendicular' and a['2']['particle']['width_px'] >= before[2]-1e-6
    assert a['2']['manual_measurements']['width'] == a['2']['particle']['width_line']
    editor.mutate(state, rev(state), 'undo')
    assert state['annotations']['2']['measurement_methods']['width'] == 'auto_feret_min' and state['annotations']['2']['particle']['width_px'] == before[2]
    with pytest.raises(ValueError, match='Choose Minimum or Perpendicular'): editor.particle_width_mode(state, dict(rev(state), mode='x'))


def test_minimum_width_line_touches_the_particle_across_a_dent():
    from lab_geometry import particle_segments
    m = np.zeros((200, 200), bool); m[50:150, 40:60] = True; m[50:150, 100:120] = True; m[130:150, 40:120] = True; m[50:90, 60:100] = False   # U: the hull bridges the notch
    for mask in (m, m.T, polygon((300, 300), [[40, 100], [150, 60], [260, 110], [120, 150]])):
        f = feret_measure(mask); yy, xx = np.nonzero(mask); cells = np.stack([xx, yy], 1).astype(float)
        for p, q in particle_segments(f['width_line'], touch=f['width_touch'])[1:]:   # each end line holds a point of the particle
            d = (q-p)/np.linalg.norm(q-p); rel = cells-p; along = rel@d
            off = np.abs(rel@np.array([-d[1], d[0]]))
            assert ((off < 1.5) & (along > -1.5) & (along < np.linalg.norm(q-p)+1.5)).any()


def test_correction_factor_scales_lengths_not_detection(lab):
    editor, state = lab
    plain = editor.detect_particles(dict(state, masks={}, annotations={}, history=[], next_id=1, revision=0, report=dict(state['report'])), {'revision': 0})['excluded']
    state['report']['scale'] = dict(um_per_pixel=UMP*1.1, image_um_per_pixel=UMP, scale_factor=1.1)
    r = editor.detect_particles(state, rev(state))
    assert r['excluded'] == plain   # detection sizes use the image scale
    row = editor.measurements(state)['candidates'][0]
    p = state['annotations'][str(row['candidate_id'])]['particle']
    assert row['length_um'] == pytest.approx(p['length_px']*UMP*1.1) and row['width_um'] == pytest.approx(p['width_px']*UMP*1.1)
    assert editor.workflow.last_scale_factor() == 1.   # nothing saved yet
    editor.workflow.root.mkdir(parents=True, exist_ok=True)
    (editor.workflow.root/'scale_factor.json').write_text('{"scale_factor": 1.05}', encoding='utf-8')
    assert editor.workflow.last_scale_factor() == 1.05


def test_image_library_carries_the_source_folder(tmp_path, monkeypatch):
    from lab_editor import LabEditor
    from pore_editor import Editor
    editor = LabEditor(output_root=tmp_path/'edits', project_root=tmp_path/'projects', device='cpu')
    monkeypatch.setattr(Editor, 'image_library', lambda self: [dict(id='a', name='a.tif'), dict(id='b', name='b.tif')])
    editor.remember_source('a', tmp_path/'run1'/'a.tif')
    assert [e['folder'] for e in editor.image_library()] == [str(tmp_path/'run1'), None]   # b: opened before folders were recorded


def test_drawn_particle_mask_follows_its_lines(lab):
    editor, state = lab
    r = editor.particle_line(state, dict(rev(state), axis='length', points=[[20, 150], [60, 150]]))   # free background: a new line-only particle
    i = r['object_id']
    editor.particle_line(state, dict(rev(state), axis='width', object_id=i, points=[[40, 140], [40, 165]]))
    ys, xs = np.nonzero(state['masks'][i])
    assert ys.min() <= 141 and ys.max() >= 164   # the mask now covers the width line too
    editor.particle_line(state, dict(rev(state), axis='length', object_id=i, points=None))
    ys, xs = np.nonzero(state['masks'][i])
    assert xs.max()-xs.min() <= 4   # only the width line is left
    r = editor.particle_line(state, dict(rev(state), axis='width', object_id=i, points=None))
    assert r['removed'] and i not in state['masks'] and str(i) not in state['annotations']   # no line left: the particle is gone
