"""LabImage application service; LabImage supplies the revision/report machinery."""
import copy
import hashlib
import json
import numpy as np
from PIL import Image
from pathlib import Path
from pore_editor import Editor, make_handler as original_handler, png_url
from lab_workflow import LabWorkflow
from lab_geometry import geometry, measured_overlay
from result_paths import replace_file


TUBE_KINDS = ('td', 't', 'd')   # length + width, length only, width only


def tube_annotation(c, kind='td'):
    from cnt_detect import VERSION
    measurements, methods = {}, {}
    if 't' in kind: measurements['length'], methods['length'] = c['path'].tolist(), 'auto_centerline'
    if 'd' in kind and c['width_px'] is not None: measurements['width'], methods['width'] = c['width_line'], 'manual_width' if c.get('width_edges') else 'auto_width'
    extra = dict(width_edges=c['width_edges']) if 'd' in kind and c.get('width_edges') else {}
    return dict(**extra, source={'trace': 'cnt_trace', 'manual': 'cnt_manual', 'sam': 'prompted_sam', 'spot': 'cnt_spot'}[c['source']], supplemental=True,
        review_status='user_accepted', manual_measurements=measurements, measurement_methods=methods,
        tube=dict(version=VERSION, kind=kind, candidate_source=c['source'], learned=bool(c.get('learned')), width_stations=c['width_stations'] if 'd' in kind else [],
                  width_station=c['width_station'] if 'd' in kind else None))


WIDTH_METHODS = dict(min='auto_feret_min', perpendicular='auto_feret_perpendicular')


def particle_annotation(measure, source, features=None, warning=None, width='min'):
    """Maximum Feret length + minimum Feret width of one flake; the lines feed the same table/CSV path as a tube's manual lines."""
    lines = dict(length=measure.get('length_line'), width=measure.get('width_line'))
    present = {k: v for k, v in lines.items() if v is not None}
    return dict(source=f'particle_{source}', supplemental=True, review_status='user_accepted', manual_measurements=present,
        measurement_methods={k: 'manual_line' if source == 'manual' else 'auto_feret' if k == 'length' else WIDTH_METHODS[width] for k in present},
        particle=dict(length_line=lines['length'], width_line=lines['width'], length_px=measure.get('length_px'), width_px=measure.get('width_px'),
                      width_caliper_px=measure.get('width_caliper_px'), width_chord_px=measure.get('width_chord_px'), width_touch=measure.get('width_touch'),
                      source=source, features=features or {}, warning=warning))


def image_scale(state):
    """µm per pixel of the image itself, for detection sizes. Reported lengths use scale['um_per_pixel'], which includes the correction factor."""
    scale = state['report']['scale']
    return scale.get('image_um_per_pixel', scale['um_per_pixel'])


def segments_cross(a, b, c, d):
    side = lambda p, q, r: (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    return side(a, b, c)*side(a, b, d) < 0 and side(c, d, a)*side(c, d, b) < 0


class LabEditor(Editor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.workflow = LabWorkflow(self, self.workflow.root, self.workflow.image_exporter)

    def measurements(self, state):
        result = super().measurements(state)
        result['measurement_unit'] = state['report'].get('measurement_unit', 'µm')
        result['stats']['measurement_unit'] = result['measurement_unit']
        result['particle_width_mode'] = self.width_mode(state)
        return result

    def width_mode(self, state):
        """'perpendicular' while any automatic width line of this analysis is the old one (perpendicular to the length), else 'min'."""
        return 'perpendicular' if any(a.get('measurement_methods', {}).get('width') == WIDTH_METHODS['perpendicular'] for a in state['annotations'].values() if 'particle' in a) else 'min'

    def particle_width_mode(self, state, payload):
        """Switch every automatic width line between minimum Feret and the Feret perpendicular to the length. Hand-drawn width lines stay. One revision (one undo)."""
        self.particle_mode(state)
        mode = payload.get('mode')
        if mode not in WIDTH_METHODS: raise ValueError('Choose Minimum or Perpendicular.')
        annotations, changed = self.width_annotations(state, mode)
        if not changed: raise ValueError('No automatic width line to change.')
        result = self.save(state, dict(state['masks']), annotations, list(state['history'])+[state['revision']], state['next_id'], dict(type='particle-width-mode', mode=mode, object_ids=changed))
        result.update(object_ids=changed, mode=mode)
        return result

    def width_annotations(self, state, mode):
        """(annotations, changed ids): a copy in which every automatic width line is measured as `mode`. Hand-drawn width lines are the same in both."""
        from particle_detect import feret_measure
        annotations, changed = copy.deepcopy(state['annotations']), []
        for i in self.particle_objects(state):
            a = annotations[str(i)]
            if a.get('measurement_methods', {}).get('width') not in WIDTH_METHODS.values() or a['measurement_methods']['width'] == WIDTH_METHODS[mode]: continue
            f = feret_measure(state['masks'][i], mode)
            a['manual_measurements']['width'] = f['width_line']; a['measurement_methods']['width'] = WIDTH_METHODS[mode]
            a['particle'].update(width_line=f['width_line'], width_px=f['width_px'], width_caliper_px=f['width_caliper_px'], width_touch=f['width_touch'])
            changed.append(i)
        return annotations, changed

    def state(self, dataset):
        state = super().state(dataset)
        if 'rgb' not in state:
            source = state['report'].get('rgb_image')
            state['rgb'] = np.array(Image.open(source).convert('RGB'))[:state['gray'].shape[0]] if source else np.repeat(state['gray'][:, :, None], 3, axis=2)
            state['sam_rgb'] = np.array(Image.open(state['report']['sam_input_image']).convert('RGB'))
            options = self.output_root/dataset/'figure_options.json'
            if options.is_file(): state['figure_options'] = json.loads(options.read_text(encoding='utf-8'))
        return state

    def response(self, state, include_measurements=True):
        info = getattr(getattr(self.predictor, 'model', None), 'intel_gpu_info', {})
        if info.get('active_device') == 'cpu':
            self.device = 'cpu'
            state['runtime_notice'] = info.get('notice')
        if state['report'].get('workspace_mode') == 'labeling':
            from lab_fast_labels import response
            result = response(self, state)
            result['runtime_notice'] = state.get('runtime_notice')
            return result
        result = super().response(state, include_measurements)
        result.update(image=png_url(Image.fromarray(state['rgb'])),
            workspace_mode=state['report'].get('workspace_mode', 'report'),
            inference_device=self.device,
            runtime_notice=state.get('runtime_notice'),
            measurement_unit=state['report'].get('measurement_unit', 'µm'))
        return result

    def save(self, state, *args, **kwargs):
        state.pop('geometry_cache', None)
        if state['report'].get('workspace_mode') == 'labeling':
            from lab_fast_labels import save
            return save(self, state, *args, **kwargs)
        return super().save(state, *args, **kwargs)

    def snapshot(self, state, revision):
        if (self.revision_folder(state['dataset'], revision)/'label_crops.npz').is_file():
            from lab_fast_labels import snapshot
            return snapshot(self, state, revision)
        return super().snapshot(state, revision)

    def manual_measurement(self, state, payload):
        if state['report'].get('workspace_mode') != 'report':
            raise ValueError('Measurements are available in report mode.')
        identifier = payload.get('object_id')
        if type(identifier) is not int or identifier not in state['masks']:
            raise ValueError('Choose a segmented object first.')
        if payload.get('reset_automatic') is True:
            annotations = copy.deepcopy(state['annotations'])
            annotation = annotations.setdefault(str(identifier), {})
            annotation.pop('manual_measurements', None)
            annotation.pop('measurement_methods', None)
            return self.save(state, dict(state['masks']), annotations,
                list(state['history'])+[state['revision']], state['next_id'],
                dict(type='automatic-measurements', object_id=identifier))
        axis = payload.get('axis')
        if axis not in ('length', 'width'): raise ValueError('Choose L or W.')
        points = payload.get('points')
        if not isinstance(points, list) or not 2 <= len(points) <= 10000:
            raise ValueError('Draw a path with 2 to 10000 points.')
        path = np.asarray(points, dtype=float)
        if path.shape != (len(points), 2) or not np.isfinite(path).all():
            raise ValueError('Invalid measurement coordinates.')
        h, w = state['gray'].shape
        if (path < 0).any() or (path[:, 0] >= w).any() or (path[:, 1] >= h).any():
            raise ValueError('Keep the path inside the image.')
        if np.linalg.norm(np.diff(path, axis=0), axis=1).sum() <= 0:
            raise ValueError('Choose distinct start and end points.')
        method = payload.get('method', 'object_path' if len(path) == 2 else 'drawn_path')
        if method not in ('object_path', 'drawn_path'):
            raise ValueError('Invalid measurement method.')
        if method == 'object_path':
            from lab_geometry import center_connected_path
            path = center_connected_path(state['masks'][identifier], path)
            method = 'object_path_via_center'
        annotations = copy.deepcopy(state['annotations'])
        annotations.setdefault(str(identifier), {}).setdefault('manual_measurements', {})[axis] = path.tolist()
        annotations[str(identifier)].setdefault('measurement_methods', {})[axis] = method
        history = list(state['history']) + [state['revision']]
        return self.save(state, dict(state['masks']), annotations, history, state['next_id'],
            dict(type='manual-measurement', object_id=identifier, axis=axis))

    def tube_ridge(self, state):
        if state['report'].get('workspace_mode') != 'report':
            raise ValueError('Tubes are available in report mode.')
        if 'tube_cache' not in state:  # gray never changes within a dataset, so this survives revisions and undo
            from cnt_detect import centerline_map, ridge_response
            state['tube_cache'] = ridge_response(state['gray'], image_scale(state),
                state['report'].get('measurement_unit', 'µm') != 'px')
            state['tube_cache']['P'] = centerline_map(state['gray'])  # None without the model file
        return state['tube_cache']

    def tube_values(self, state, c, kind='td'):
        """What the user sees for one tube; nested under `tube` in the response so it cannot clobber image fields."""
        ump = state['report']['scale']['um_per_pixel']
        width = float(np.linalg.norm(np.diff(c['width_line'], axis=0))) if 'd' in kind and c['width_line'] else None  # what the table and CSV report
        length = c['length_px'] if 't' in kind else None
        station = c['width_station'] if width is not None else None
        return dict(kind=kind, length_px=length, width_px=width, length=None if length is None else length*ump,
            width=None if width is None else width*ump, unit=state['report'].get('measurement_unit', 'µm'),
            clean=None if station is None else station['clean'])

    def trace_tube(self, state, payload):
        """Trace the ridge through the clicked points (or under a freehand stroke, or measure D at one click) and save one measured object."""
        from cnt_detect import STROKE_MAX_POINTS, manual_line, measure_spot, trace_stroke, trace_tube
        ridge = self.tube_ridge(state)
        kind, points = payload.get('kind', 'td'), payload.get('points')
        if kind not in TUBE_KINDS: raise ValueError('Invalid tube kind.')
        if payload.get('stroke') is True:
            if kind == 'd': raise ValueError('A stroke measures length: use kind td or t.')
            if not isinstance(points, list) or not 2 <= len(points) <= STROKE_MAX_POINTS: raise ValueError(f'A stroke needs 2 to {STROKE_MAX_POINTS} points.')
            c = trace_stroke(state['gray'], ridge, points)   # the stroke may run past the border: it is clipped to the image
            if payload.get('preview') is True:   # live preview while dragging: nothing is saved
                return dict(preview=True, path=np.round(c['path'], 1).tolist())
            return self.add_tube(state, c, kind)
        if payload.get('manual') is True:   # the user's own polyline, saved as drawn
            if kind == 'd': raise ValueError('A line measures length: use kind td or t.')
            return self.add_tube(state, manual_line(state['gray'], ridge, points), kind)
        if kind == 'd':
            if not isinstance(points, list) or len(points) != 1: raise ValueError('Width only needs one click on the tube.')
        elif not isinstance(points, list) or not 2 <= len(points) <= 20:
            raise ValueError('Trace needs 2 to 20 points inside the image.')
        self.coords(points, state['gray'].shape)
        c = measure_spot(state['gray'], ridge, points[0]) if kind == 'd' else trace_tube(state['gray'], ridge, points)
        return self.add_tube(state, c, kind)

    def add_tube(self, state, c, kind):
        """Save a traced / measured candidate as one new tube object."""
        from cnt_detect import tube_mask
        occupied = np.zeros(state['gray'].shape, bool)
        for m in state['masks'].values(): occupied |= m
        # Pre-carving keeps masks exclusive; length and width were measured on the whole tube.
        full = tube_mask(state['gray'].shape, c['path'], c['band_px'])
        mask = full & ~occupied
        if mask.sum() < 20:
            # Name the object that covers the trace, labelled as the list and figure label it (T#, D# or #).
            hit = max(state['masks'], key=lambda i: int((state['masks'][i] & full).sum()), default=None)
            kind_ = (state['annotations'].get(str(hit)) or {}).get('tube', {}).get('kind')
            raise ValueError('This tube is already measured.' if hit is None else
                f"{'D' if kind_ == 'd' else 'T' if kind_ else '#'}{hit} is already measured.")
        identifier = state['next_id']
        annotations = copy.deepcopy(state['annotations'])
        annotations[str(identifier)] = tube_annotation(c, kind)
        result = self.save(state, {**state['masks'], identifier: mask}, annotations,
            list(state['history'])+[state['revision']], identifier+1, dict(type='trace-tube', object_id=identifier, kind=kind))
        result.update(object_id=identifier, tube=self.tube_values(state, c, kind))
        return result

    def measure_box(self, state, payload):
        """D inside a dragged box. Where the box crosses the centerline of an existing object, D is measured on the part of that
        path inside the box and replaces the object's D (a length-only tube becomes length + width); otherwise a new width-only
        object is measured at the box. A width-only object whose mark lies in the box has its D replaced too."""
        from cnt_detect import box_piece, box_width, clean_box, measure_spot
        ridge = self.tube_ridge(state)
        box = clean_box(payload.get('box'), state['gray'].shape)
        centre = np.array([(box[0]+box[2])/2, (box[1]+box[3])/2])
        hits, marks = [], []
        for identifier in state['masks']:
            paths = (state['annotations'].get(str(identifier)) or {}).get('manual_measurements') or {}
            if len(paths.get('length', [])) > 1:
                piece = box_piece(paths['length'], box)
                if piece is not None: hits.append((len(piece), identifier, piece))
            elif len(paths.get('width', [])) > 1:
                mid = np.mean(np.asarray(paths['width'], float), axis=0)
                if box[0] <= mid[0] <= box[2] and box[1] <= mid[1] <= box[3]: marks.append((float(np.linalg.norm(mid-centre)), identifier))
        if not hits and not marks:
            return dict(self.add_tube(state, measure_spot(state['gray'], ridge, centre, box), 'd'), replaced=False)
        if hits:
            _, identifier, piece = max(hits)
            m = box_width(state['gray'], ridge, piece, box)
        else:
            _, identifier = min(marks)
            m = measure_spot(state['gray'], ridge, centre, box)
        annotations = copy.deepcopy(state['annotations'])
        annotation = annotations[str(identifier)]
        annotation.pop('width_edges', None)   # an automatic D replaces a hand-drawn one
        measured = annotation.setdefault('manual_measurements', {})
        measured['width'] = m['width_line']
        annotation.setdefault('measurement_methods', {})['width'] = 'auto_width'
        length = np.asarray(measured.get('length', []), float)
        kind = 'td' if len(length) > 1 else 'd'
        if 'tube' in annotation: annotation['tube'].update(kind=kind, width_stations=m['width_stations'], width_station=m['width_station'])
        result = self.save(state, dict(state['masks']), annotations, list(state['history'])+[state['revision']], state['next_id'],
            dict(type='box-width', object_id=identifier))
        c = dict(width_line=m['width_line'], width_station=m['width_station'], length_px=float(np.linalg.norm(np.diff(length, axis=0), axis=1).sum()) if kind == 'td' else None)
        result.update(object_id=identifier, replaced=True, tube=self.tube_values(state, c, kind))
        return result

    def measure_edges(self, state, payload):
        """D from two parallel lines (hand-label style): `edge` is the user's line along one side of the tube, `point` a click on
        the other side. D is their perpendicular distance. Where the strip between the lines crosses an object's length path,
        that object's D is replaced; otherwise a new width-only object is made."""
        import cv2
        edge, point = payload.get('edge'), payload.get('point')
        if not isinstance(edge, list) or len(edge) != 2 or not isinstance(point, list): raise ValueError('Draw one edge line, then click the other side.')
        a0, a1 = np.asarray(self.coords(edge, state['gray'].shape), float)
        p = np.asarray(self.coords([point], state['gray'].shape), float)[0]
        span = float(np.linalg.norm(a1-a0))
        if span < 2: raise ValueError('Draw a longer edge line.')
        u = (a1-a0)/span; n = np.array([-u[1], u[0]])
        d = float((p-a0)@n)
        if abs(d) < 1: raise ValueError('Click the other side of the tube.')
        b0, b1 = a0+d*n, a1+d*n
        mid = (a0+a1)/2
        width_line = [mid.tolist(), (mid+d*n).tolist()]
        edges = [[a0.tolist(), a1.tolist()], [b0.tolist(), b1.tolist()]]
        strip = np.zeros(state['gray'].shape, np.uint8)
        cv2.fillPoly(strip, [np.rint([a0, a1, b1, b0]).astype(np.int32)], 1)
        hits = []
        for identifier in state['masks']:
            annotation = state['annotations'].get(str(identifier)) or {}
            paths = annotation.get('manual_measurements') or {}
            if len(paths.get('length', [])) > 1:
                from cnt_detect import resample
                q = np.rint(resample(paths['length'])).astype(int)
                q = q[(q[:, 0] >= 0) & (q[:, 1] >= 0) & (q[:, 0] < strip.shape[1]) & (q[:, 1] < strip.shape[0])]
                inside = int(strip[q[:, 1], q[:, 0]].sum()) if len(q) else 0
                if inside: hits.append((inside, identifier))
        if not hits:
            c = dict(source='manual', path=np.array([(a0+b0)/2, (a1+b1)/2]), band_px=abs(d), width_px=abs(d), width_line=width_line,
                     width_edges=edges, width_stations=[], width_station=None, length_px=span)
            return dict(self.add_tube(state, c, 'd'), replaced=False)
        identifier = max(hits)[1]
        annotations = copy.deepcopy(state['annotations'])
        annotation = annotations[str(identifier)]
        measured = annotation.setdefault('manual_measurements', {})
        measured['width'] = width_line
        annotation['width_edges'] = edges
        annotation.setdefault('measurement_methods', {})['width'] = 'manual_width'
        length = np.asarray(measured.get('length', []), float)
        if 'tube' in annotation: annotation['tube'].update(kind='td', width_stations=[], width_station=None)
        result = self.save(state, dict(state['masks']), annotations, list(state['history'])+[state['revision']], state['next_id'],
            dict(type='edge-width', object_id=identifier))
        c = dict(width_line=width_line, width_station=None, length_px=float(np.linalg.norm(np.diff(length, axis=0), axis=1).sum()))
        result.update(object_id=identifier, replaced=True, tube=self.tube_values(state, c, 'td'))
        return result

    def particle_values(self, state, p):
        """What the user sees for one particle, in the report unit; nested under `particle` in the response."""
        ump = state['report']['scale']['um_per_pixel']
        scaled = lambda v: None if v is None else v*ump
        return dict(length=scaled(p['length_px']), width=scaled(p['width_px']), unit=state['report'].get('measurement_unit', 'µm'),
            length_px=p['length_px'], width_px=p['width_px'])

    def particle_objects(self, state):
        return [i for i in state['masks'] if 'particle' in state['annotations'].get(str(i), {})]

    def particle_mode(self, state):
        """The image scale for detection sizes (without the correction factor)."""
        if state['report'].get('workspace_mode') != 'report': raise ValueError('Particles are available in report mode.')
        return image_scale(state)

    def free_mask(self, state, mask):
        occupied = np.zeros(mask.shape, bool)
        for m in state['masks'].values(): occupied |= m
        return mask & ~occupied

    def add_particles(self, state, items, kind):
        """Save new particle objects ((mask, annotation) pairs) as ONE revision."""
        masks, annotations, next_id, ids = dict(state['masks']), copy.deepcopy(state['annotations']), state['next_id'], []
        for mask, annotation in items:
            masks[next_id], annotations[str(next_id)] = mask, annotation
            ids.append(next_id); next_id += 1
        result = self.save(state, masks, annotations, list(state['history'])+[state['revision']], next_id, dict(type=kind, object_ids=ids))
        return result, ids

    def automatic_masks(self, state):
        """SAM automatic masks of the analysis image (Labeling settings), resolved to exclusive masks."""
        from particle_detect import SAM_SETTINGS, resolve_proposals
        from sam_runtime import build_runtime_model, inference_context, release_device_cache
        from segment_first_pass import ProgressGenerator
        with inference_context(self.device):
            if self.predictor is None:
                from sam2.sam2_image_predictor import SAM2ImagePredictor
                self.predictor = SAM2ImagePredictor(build_runtime_model(self.device))
            generator = ProgressGenerator(self.predictor.model, points_per_batch=1 if self.device == 'intel-gpu' else 8, **SAM_SETTINGS)
            try: proposals = generator.generate(state['sam_rgb'])
            finally: release_device_cache(self.device)
        return resolve_proposals(proposals, state['gray'].shape)

    def point_masks(self, state, point):
        """SAM masks for one positive click, best score first."""
        self.preview(state, dict(revision=state['revision'], points=[point], labels=[1], fill_holes=False, _defer_preview_images=True))
        return state['preview']['masks']

    def detect_particles(self, state, payload):
        """Every SAM mask that passes the particle rules becomes one measured object, all in one revision (one undo)."""
        from particle_detect import FEATURE_KEYS, detect_particles
        ump = self.particle_mode(state)
        width = self.width_mode(state)   # a new detection follows the lines already there
        kept, excluded = detect_particles(state['gray'], self.automatic_masks(state), ump, width)
        existing, items = list(state['masks'].values()), []
        occupied = np.zeros(state['gray'].shape, bool)
        for m in existing: occupied |= m
        for p in kept:
            m = p['mask']
            if (m & occupied).sum() > .5*m.sum() or any((m & e).sum() > .5*e.sum() for e in existing): continue   # already measured
            fresh = m & ~occupied
            items.append((fresh, particle_annotation(p['feret'], 'auto', {k: round(p[k], 3) for k in FEATURE_KEYS}, width=width)))
            occupied |= fresh
        if not items: raise ValueError('No measurable particle found. Click a particle or draw the lines by hand.')
        result, ids = self.add_particles(state, items, 'detect-particles')
        result.update(object_ids=ids, excluded=excluded)
        return result

    def measure_particle(self, state, payload):
        """One click: SAM mask under the point -> maximum Feret length + minimum Feret width. Rules are not applied; the one that would fire is a warning."""
        from particle_detect import FEATURE_KEYS, exclusion_reason, particle_features
        from scipy import ndimage as ndi
        ump = self.particle_mode(state)
        if not isinstance(payload.get('point'), list) or len(payload['point']) != 2: raise ValueError('Click inside a particle.')
        x, y = np.floor(self.coords([payload['point']], state['gray'].shape)[0]).astype(int)
        for i in self.particle_objects(state):
            if state['masks'][i][y, x]: raise ValueError(f'This particle is already measured as #{i}.')
        mask = self.point_masks(state, [int(x), int(y)])[0]
        labelled, _ = ndi.label(mask)
        if not labelled[y, x]: raise ValueError('No particle found at this point.')
        mask = labelled == labelled[y, x]
        fresh = self.free_mask(state, mask)
        if fresh.sum() < 20:
            hit = max(state['masks'], key=lambda i: int((state['masks'][i] & mask).sum()), default=None)
            raise ValueError('This particle is already measured.' if hit is None else f'#{hit} already covers this particle.')
        width = self.width_mode(state)
        row = particle_features([mask], state['gray'], ump, [state['masks'][i] for i in self.particle_objects(state)], width)[0]
        warning = exclusion_reason(row)
        result, ids = self.add_particles(state, [(fresh, particle_annotation(row['feret'], 'click', {k: round(row[k], 3) for k in FEATURE_KEYS if k in row}, warning, width))], 'measure-particle')
        result.update(object_id=ids[0], warning=warning, particle=self.particle_values(state, state['annotations'][str(ids[0])]['particle']))
        return result

    def particle_line(self, state, payload):
        """A hand-drawn straight line. It belongs to the particle holding its midpoint, else to the one whose other-axis line it crosses, else to a new object.
        `points: null` with `object_id` removes that axis line instead (the object and its mask stay)."""
        from cnt_detect import tube_mask
        self.particle_mode(state)
        axis, points, identifier = payload.get('axis'), payload.get('points'), payload.get('object_id')
        if axis not in ('length', 'width'): raise ValueError('Choose L or W.')
        if points is None:
            if identifier not in self.particle_objects(state): raise ValueError('Choose a measured particle first.')
            annotations = copy.deepcopy(state['annotations'])
            annotation = annotations[str(identifier)]
            if axis not in annotation['manual_measurements']: raise ValueError(f'This particle has no {axis} line.')
            del annotation['manual_measurements'][axis]; annotation['measurement_methods'].pop(axis, None)
            annotation['particle'].update({f'{axis}_line': None, f'{axis}_px': None})
            result = self.save(state, dict(state['masks']), annotations, list(state['history'])+[state['revision']], state['next_id'],
                dict(type='particle-line-remove', object_id=identifier, axis=axis))
            result.update(object_id=identifier, created=False, particle=self.particle_values(state, annotation['particle']))
            return result
        if not isinstance(points, list) or len(points) != 2: raise ValueError('Draw one straight line with two points.')
        line = np.asarray(points, dtype=float)
        if line.shape != (2, 2) or not np.isfinite(line).all(): raise ValueError('Invalid measurement coordinates.')
        h, w = state['gray'].shape
        if (line < 0).any() or (line[:, 0] >= w).any() or (line[:, 1] >= h).any(): raise ValueError('Keep the line inside the image.')
        if np.linalg.norm(line[1]-line[0]) <= 0: raise ValueError('Choose distinct start and end points.')
        particles = self.particle_objects(state)
        if identifier is not None and identifier not in particles: raise ValueError('Choose a measured particle first.')
        if identifier is None:
            x, y = np.minimum(np.floor((line[0]+line[1])/2+.5).astype(int), [w-1, h-1])
            identifier = next((i for i in particles if state['masks'][i][y, x]), None)
        if identifier is None:
            other = 'width' if axis == 'length' else 'length'
            crossed = [(float(np.linalg.norm((line[0]+line[1])/2-np.mean(q, axis=0))), i) for i in particles
                       if (q := state['annotations'][str(i)]['manual_measurements'].get(other)) and segments_cross(line[0], line[1], *q)]
            identifier = min(crossed)[1] if crossed else None
        created, length = identifier is None, float(np.linalg.norm(line[1]-line[0]))
        if created:
            mask = self.free_mask(state, tube_mask(state['gray'].shape, line, 3))
            if mask.sum() < 20: raise ValueError('Draw the line on free background, outside the measured objects.')
            result, ids = self.add_particles(state, [(mask, particle_annotation({f'{axis}_line': line.tolist(), f'{axis}_px': length}, 'manual'))], 'particle-line')
            identifier = ids[0]
        else:
            annotations = copy.deepcopy(state['annotations'])
            annotation = annotations[str(identifier)]
            annotation['manual_measurements'][axis] = line.tolist()
            annotation.setdefault('measurement_methods', {})[axis] = 'manual_line'
            annotation['particle'].update({f'{axis}_line': line.tolist(), f'{axis}_px': length})
            result = self.save(state, dict(state['masks']), annotations, list(state['history'])+[state['revision']], state['next_id'],
                dict(type='particle-line', object_id=identifier, axis=axis))
        result.update(object_id=identifier, created=created, particle=self.particle_values(state, state['annotations'][str(identifier)]['particle']))
        return result

    def label_figure(self, state, length, width, font_size=16):
        """Yellow hand-label style figure (lengths and/or widths, no fill, no ids) on the whole image."""
        from lab_geometry import measured_overlay
        figure = measured_overlay(state, opacity=0, show_ids=False, show_length=length, show_width=width, font_size=font_size)
        full = state['report'].get('rgb_image')
        if full:   # the editor works above the SEM info bar; the saved figure keeps the whole image, bar included
            whole = Image.open(full).convert('RGB'); whole.paste(figure, (0, 0)); figure = whole
        return figure

    def save_labels(self, state, payload):
        """Hand-label figures beside the original: <name>(2) with lengths (T#) only, <name>(3) with widths (D#) only; particles: plain values, label = object id.
        Particles also get <name>(1): the minimum Feret widths. Their <name>(3) is the width perpendicular to the length. Both are saved whatever the Width toggle shows."""
        if not any('tube' in a or 'particle' in a for a in state['annotations'].values()): return dict(no_tubes=True)
        source = self.source_path(state)
        folder = payload.get('directory')
        if folder: folder = Path(folder)
        elif source: folder = source.parent
        else: return dict(need_folder=True)
        if not folder.is_absolute() or not folder.is_dir(): raise ValueError('Choose an existing folder.')
        name = Path(state['report'].get('source_name', 'image'))   # original file name: only (2) / (3) is added, the extension stays
        stem, suffix = (source.stem, source.suffix) if source else (name.stem, name.suffix if name.suffix.lower() in ('.tif', '.tiff', '.png', '.jpg', '.jpeg') else '.png')
        def view(mode):   # this analysis with every automatic width line measured as `mode`
            other = dict(state, annotations=self.width_annotations(state, mode)[0]); other.pop('measurements', None)
            return other
        particles = any('particle' in a for a in state['annotations'].values())
        # (tag, state to draw, length?, width?, CSV label prefix, row key, CSV column)
        jobs = [('(2)', state, True, False, 'T', 'length_um', 'length'), ('(3)', view('perpendicular') if particles else state, False, True, 'D', 'width_um', 'width')]
        if particles: jobs.insert(0, ('(1)', view('min'), False, True, 'D', 'width_um', 'min_feret_width'))
        targets = [folder/f'{stem}{job[0]}{suffix}' for job in jobs]
        tables = [folder/f'{stem}{job[0]}.csv' for job in jobs]   # T# lengths / D# widths, as on the figures
        # Existing name(1) / name(2) / name(3) files are replaced without asking: saving again after an edit is the normal case.
        for target, (_, shown, length, width, *_) in zip(targets, jobs):
            figure = self.label_figure(shown, length, width, int(payload.get('font_size', 16)))
            partial = target.with_name('.'+target.name+'.partial')
            figure.save(partial, format={'.tif': 'TIFF', '.tiff': 'TIFF', '.jpg': 'JPEG', '.jpeg': 'JPEG'}.get(suffix.lower(), 'PNG'))
            replace_file(partial, target)
        import csv
        unit = state['report'].get('measurement_unit', 'µm')
        for table, (_, shown, _, _, prefix, key, name) in zip(tables, jobs):
            rows = [r for r in self.measurements(shown)['candidates'] if r.get('tube') or r.get('particle')]
            partial = table.with_name('.'+table.name+'.partial')
            with open(partial, 'w', newline='', encoding='utf-8-sig') as out:   # utf-8-sig: Excel reads µm correctly
                writer = csv.writer(out)
                writer.writerow(['label', f'{name}_{unit}'])
                for r in rows:
                    if r.get(key) is not None: writer.writerow([r['candidate_id'] if r.get('particle') else f"{prefix}{r['candidate_id']}", f"{r[key]:.2f}"])
            replace_file(partial, table)
        return dict(saved=[str(t) for t in targets+tables])

    def source_path(self, state):
        """Where the user opened this image from (recorded by the desktop Open dialog), if that file still exists."""
        for project in self.workflow.projects.values():
            if any(r['dataset'] == state['dataset'] for r in project['runs']):
                path = self.source_paths().get(project.get('source_sha256', ''))
                return Path(path) if path and Path(path).is_file() else None
        return None

    def source_paths(self):
        f = self.output_root/'source_paths.json'
        try: return json.loads(f.read_text(encoding='utf-8'))
        except (OSError, ValueError): return {}

    # --- Batch: every image of a folder -> calibrate from its file, detect particles, save name(1)/(2)/(3) + CSVs beside it.
    def batch_start(self, payload):
        import re, threading
        folder = Path(str(payload.get('directory') or ''))
        if not folder.is_absolute() or not folder.is_dir(): raise ValueError('Choose an existing folder.')
        if getattr(self, 'batch', None) and self.batch['running']: raise ValueError('A batch is already running.')
        files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ('.tif', '.tiff', '.png', '.jpg', '.jpeg')
                       and not re.search(r'\(\d+\)$', p.stem))   # name(1) / name(2) / name(3) are results, not inputs
        if not files: raise ValueError('No images in this folder.')
        self.batch = dict(running=True, stop=False, folder=str(folder), total=len(files), done=0, current=None, results=[])
        threading.Thread(target=self.batch_run, args=(files, payload.get('overwrite') is True), daemon=True).start()
        return self.batch_status()

    def batch_status(self):
        return copy.deepcopy(getattr(self, 'batch', None) or dict(running=False, total=0, done=0, current=None, results=[]))

    def batch_stop(self):
        if getattr(self, 'batch', None): self.batch['stop'] = True
        return self.batch_status()

    def batch_run(self, files, overwrite):
        b = self.batch
        for path in files:
            if b['stop']: break
            b['current'] = path.name
            row = dict(name=path.name)
            try:
                # Done = name(1), name(2) and name(3) are all there. An image without (1) (results older than the minimum Feret width) is analysed again.
                if not overwrite and all(path.with_name(f'{path.stem}({n}){path.suffix}').exists() for n in (1, 2, 3)):
                    row.update(status='skipped', note='already has (1), (2) and (3)')
                else: row.update(self.batch_one(path, overwrite))
            except Exception as error:   # one bad image must not stop the folder
                row.update(status='failed', note=str(error))
            b['results'].append(row); b['done'] += 1
        b.update(running=False, current=None)

    def batch_one(self, path, overwrite):
        import time
        content = path.read_bytes()
        opened = self.receive_image(path.name, content)
        self.remember_source(hashlib.sha256(content).hexdigest(), path)
        project = self.workflow.inspect(opened['project']['id'] if 'project' in opened else opened['image']['project_id'])
        c, meta = project['config'], project.get('scale_metadata') or {}
        pixels = meta.get('length_pixels') or (c.get('scale_pixels') if c.get('calibrated') else None) or 100
        scale = meta.get('label_um') or (pixels*meta['um_per_pixel'] if meta else c.get('scale_um') if c.get('calibrated') else None)
        config = dict(analysis_bottom=c['analysis_bottom'], preprocessing_mode='adjustable', normalize_enabled=False, background_strength=0, blur_method='none',
            blur_strength=0, scale_um=scale or 1, scale_pixels=pixels if scale else 1, scale_factor=self.workflow.last_scale_factor(), min_contrast=0, min_area_pixels=1, points_per_side=16,
            scale_confirmed=True, workspace_mode='report', calibrated=bool(scale))
        job = self.workflow.start(project['id'], config)['job_id']
        while True:
            status = self.workflow.status(job)
            if status['status'] in ('complete', 'failed', 'cancelled'): break
            if self.batch['stop']: self.workflow.cancel(job)
            time.sleep(.2)
        if status['status'] != 'complete': raise ValueError(status.get('message') or 'Analysis did not finish.')
        with self.lock:
            state = self.state(status['dataset'])
            try: found = self.detect_particles(state, dict(revision=state['revision']))
            except ValueError as error: return dict(status='no particles', note=str(error), dataset=status['dataset'])
            self.save_labels(state, dict(overwrite=overwrite))
        return dict(status='saved', particles=len(found['object_ids']), excluded=sum(found['excluded'].values()),
                    unit='µm' if scale else 'px', dataset=status['dataset'])

    def remember_source(self, digest, path):
        paths = self.source_paths(); paths[digest] = str(path)
        self.output_root.mkdir(parents=True, exist_ok=True)   # a fresh install has no edits folder yet
        (self.output_root/'source_paths.json').write_text(json.dumps(paths, ensure_ascii=False, indent=1), encoding='utf-8')

    def measure_tube(self, state, payload):
        """Automatic centerline and width for an existing (SAM) mask, or D inside a `box`."""
        from cnt_detect import measure_mask
        if payload.get('box') is not None: return self.measure_box(state, payload)
        if payload.get('edge') is not None: return self.measure_edges(state, payload)
        ridge = self.tube_ridge(state)
        identifier = payload.get('object_id')
        if type(identifier) is not int or identifier not in state['masks']:
            raise ValueError('Choose a segmented object first.')
        c = measure_mask(state['gray'], state['masks'][identifier], ridge)
        annotations = copy.deepcopy(state['annotations'])
        annotations.setdefault(str(identifier), {}).update({k: v for k, v in tube_annotation(c).items() if k not in ('source', 'supplemental', 'review_status')})
        result = self.save(state, dict(state['masks']), annotations, list(state['history'])+[state['revision']],
            state['next_id'], dict(type='tube-measurement', object_id=identifier))
        result.update(tube=self.tube_values(state, c))
        return result

    def quick_segment(self, state, payload):
        self.check_revision(state, payload)
        points, labels = payload.get('points', []), payload.get('labels', [])
        if not points: raise ValueError('Click inside an object first.')
        coords = self.coords(points, state['gray'].shape)
        target = payload.get('target_id')
        if target is not None and target in state['masks'] and 1 not in labels:
            import cv2
            mask = state['masks'][target]
            y,x = np.unravel_index(cv2.distanceTransform(mask.astype(np.uint8),cv2.DIST_L2,3).argmax(),mask.shape)
            points, labels = [[int(x),int(y)]]+points, [1]+labels
            payload = dict(payload, points=points, labels=labels)
        if target is None:
            positives = [p for p,l in zip(coords, labels) if l == 1]
            if positives:
                x,y = np.floor(positives[0]).astype(int)
                target = next((i for i,m in state['masks'].items() if m[y,x]), None)
        if target is not None and target not in state['masks']: raise ValueError('Select an existing object.')
        self.preview(state, dict(payload, fill_holes=False, _defer_preview_images=True))
        previous = state['preview']
        others = np.zeros(state['gray'].shape, bool)
        for i,m in state['masks'].items():
            if i != target: others |= m
        masks, scores = [], []
        # Preserve all other instances. A point edit cannot silently delete them.
        for m in previous['masks']:
            candidate = m & ~others
            if candidate.any(): masks.append(candidate)
        if not masks: raise ValueError('No free object pixels. Refine the points or select the object to replace.')
        instant = payload.get('auto_apply') is True and state['report'].get('workspace_mode') == 'labeling'
        result = self.preview_masks(state, dict(payload, _defer_preview_images=instant), masks, [None]*len(masks), 'prompted_sam')
        if instant:
            # Candidates above already exclude every other instance. Avoid the
            # generic apply path's redundant full-image containment/IoU scans.
            preview = state['preview']
            next_id = state['next_id']
            replaced = [] if target is None else [target]
            if target is None:
                target = next_id
                next_id += 1
            updated = dict(state['masks'])
            updated[target] = preview['masks'][0]
            annotations = copy.deepcopy(state['annotations'])
            annotations[str(target)] = dict(source=preview['source'], supplemental=True,
                review_status='user_accepted', prompts=preview['prompts'], replaced_candidate_ids=replaced)
            result = self.save(state, updated, annotations, state['history']+[state['revision']], next_id,
                dict(type='apply', candidate_id=target, source=preview['source'], prompts=preview['prompts'],
                     replaced_candidate_ids=replaced, contained_candidate_ids=[]))
            result.update(applied=True, applied_target_id=target,
                effective_points=points, effective_labels=labels)
            return result
        result['target_id'] = target
        result.update(effective_points=points, effective_labels=labels)
        return result


def make_handler(editor):
    parent = original_handler(editor)
    class Handler(parent):
        def do_GET(self):
            path = self.path.split('?',1)[0]
            if path in ('/labimage.js','/labimage.css','/theme.css','/icons.js','/units.js'):
                if not self.valid_host(): return self.send(403, dict(error='Local access only'))
                from app_paths import ASSET_ROOT
                return self.send(200, (ASSET_ROOT/'ui'/path[1:]).read_bytes(), 'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8')
            return super().do_GET()

        def do_POST(self):
            if self.path not in ('/api/quick-segment','/api/measurement-overlay','/api/manual-measurement','/api/trace-tube','/api/measure-tube','/api/detect-particles','/api/measure-particle','/api/particle-line','/api/particle-width-mode','/api/save-labels','/api/choose-image','/api/batch-particles','/api/batch-status','/api/batch-stop','/api/update-check','/api/update-install'):
                return super().do_POST()
            if not self.valid_host() or self.headers.get('X-Object-Editor') != '1':
                return self.send(403, dict(error='Local access only'))
            origin = self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'):
                return self.send(403, dict(error='Origin rejected'))
            try:
                length = int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 1_000_000: raise ValueError('Invalid request size.')
                payload = json.loads(self.rfile.read(length))
                if self.path == '/api/update-check':
                    import app_update
                    return self.send(200, app_update.check())
                if self.path == '/api/update-install':   # downloads the patch, then the app closes and a helper swaps the files
                    import app_update, threading
                    if editor.workflow.running or (getattr(editor, 'batch', None) and editor.batch['running']): raise ValueError('Wait for the current analysis.')
                    quit_app = getattr(editor, 'quit_app', None)
                    if not quit_app: raise ValueError('Updates work in the installed app.')
                    result = app_update.install(editor.output_root.parent/'update')
                    threading.Timer(1.5, quit_app).start()
                    return self.send(200, result)
                if self.path == '/api/batch-particles': return self.send(200, editor.batch_start(payload))
                if self.path == '/api/batch-status': return self.send(200, editor.batch_status())
                if self.path == '/api/batch-stop': return self.send(200, editor.batch_stop())
                if self.path == '/api/choose-image':   # desktop Open dialog: the image's folder is remembered for Save image
                    picker = getattr(editor, 'image_picker', None)
                    if not picker: raise ValueError('Use the desktop app to choose an image.')
                    path = picker()
                    if not path: return self.send(200, dict(cancelled=True))
                    path = Path(path)
                    if path.suffix.lower() not in ('.tif', '.tiff', '.png', '.jpg', '.jpeg'): raise ValueError('Choose a TIF, PNG or JPG image.')
                    content = path.read_bytes()
                    result = editor.receive_image(path.name, content)
                    editor.remember_source(hashlib.sha256(content).hexdigest(), path)
                    return self.send(200, result)
                if editor.workflow.running: raise ValueError('Wait for the current analysis.')
                with editor.lock:
                    state = editor.state(payload.get('dataset'))
                    editor.check_revision(state, payload)
                    if self.path == '/api/manual-measurement':
                        result = editor.manual_measurement(state, payload)
                    elif self.path == '/api/trace-tube':
                        result = editor.trace_tube(state, payload)
                    elif self.path == '/api/measure-tube':
                        result = editor.measure_tube(state, payload)
                    elif self.path == '/api/detect-particles':
                        result = editor.detect_particles(state, payload)
                    elif self.path == '/api/measure-particle':
                        result = editor.measure_particle(state, payload)
                    elif self.path == '/api/particle-line':
                        result = editor.particle_line(state, payload)
                    elif self.path == '/api/particle-width-mode':
                        result = editor.particle_width_mode(state, payload)
                    elif self.path == '/api/save-labels':
                        result = editor.save_labels(state, payload)
                    elif self.path == '/api/quick-segment':
                        result = editor.quick_segment(state, payload)
                    else:
                        size = payload.get('font_size',16)
                        if type(size) is not int or not 8 <= size <= 64: raise ValueError('Text size must be 8–64 px.')
                        opacity = payload.get('opacity',18)
                        if type(opacity) not in (int,float) or not np.isfinite(opacity) or not 0<=opacity<=100: raise ValueError('Opacity must be 0–100.')
                        options = dict(opacity=opacity/100, show_length=payload.get('show_length',True),
                            show_width=payload.get('show_width',True), show_ids=payload.get('show_ids',True), font_size=size)
                        if any(type(options[k]) is not bool for k in ['show_length','show_width','show_ids']): raise ValueError('Invalid figure options.')
                        if options != state.get('figure_options'):
                            state['figure_options'] = options
                            state.pop('report_content',None)
                            folder = editor.output_root/state['dataset']; folder.mkdir(parents=True,exist_ok=True)
                            (folder/'figure_options.json').write_text(json.dumps(options),encoding='utf-8')
                        result = dict(image=png_url(measured_overlay(state, **options)))
                return self.send(200, result)
            except (ValueError, KeyError, TypeError) as error:
                return self.send(400, dict(error=str(error)))
            except ConnectionError:
                return   # the page dropped the request (a live preview aborted on release): nothing to answer
            except Exception as error:
                import traceback
                traceback.print_exc()
                return self.send(500, dict(error=str(error)))
    return Handler
