"""Mode-specific runs, official SAM automatic proposals, no object heuristics."""
import copy
import json
import math
import traceback
import cv2
import numpy as np
from PIL import Image
from project_workflow import ProjectWorkflow
from app_paths import checkpoint_path
from result_paths import write_artifact
from sam_runtime import inference_context, release_device_cache
from operation_cancel import OperationCancelled


def tescan_header(path):
    """Pixel size (µm/px) and info-bar height (px) from a TESCAN TIFF header (private tag 50431), when the file has one."""
    import re
    try:
        with Image.open(path) as image: text = bytes(image.tag_v2.get(50431) or b'')
    except Exception: return {}
    found = {}
    size, strip = re.search(rb'PixelSizeX=([0-9.eE+-]+)', text), re.search(rb'ImageStripSize=(\d+)', text)
    try:
        if size and 0 < float(size.group(1)) < 1: found['um_per_pixel'] = float(size.group(1))*1e6
        if strip: found['strip'] = int(strip.group(1))
    except ValueError: pass
    return found


class LabWorkflow(ProjectWorkflow):
    # Calibration correction factor: every length is multiplied by it (areas by its square). The last one used is the default for new images.
    def last_scale_factor(self):
        try: value = float(json.loads((self.root/'scale_factor.json').read_text(encoding='utf-8'))['scale_factor'])
        except (OSError, ValueError, KeyError, TypeError): return 1.
        return value if .01 <= value <= 100 else 1.

    def upload(self, name, content, seed=None):
        result = super().upload(name, content, seed)
        project = self.projects[result['id']]
        if not seed:
            project['config'].update(scale_factor=self.last_scale_factor(), scale_um=project['config'].get('scale_um') if project.get('scale_metadata') else None,   # keep a scale read from the file
                min_contrast=0, min_area_pixels=100, points_per_side=16,
                preprocessing_mode='adjustable', normalize_enabled=False, background_strength=0,
                blur_method='none', blur_strength=0)
        # Keep source colors for general microscopy and ordinary photographs.
        original = self.root/project['id']/project['original_file']
        with Image.open(original) as image:
            if image.mode in ('RGB', 'RGBA', 'P', 'CMYK'):
                image.convert('RGB').save(original.parent/'display.png')
            else:
                Image.open(original.parent/'normalized.png').convert('RGB').save(original.parent/'display.png')
        self.persist(project)
        return self.inspect(project['id'])

    def inspect(self, project_id):
        project = self.projects[project_id]
        if 'footer_detection' not in project:
            from lab_footer import detect_information_footer
            from segment_first_pass import detect_scale_bar
            gray = np.asarray(Image.open(self.root/project_id/'input/normalized.png'))
            bottom = detect_information_footer(gray)
            header = tescan_header(self.root/project_id/project['original_file'])
            if 0 < header.get('strip', 0) < project['height']: bottom = project['height']-header['strip']   # the microscope's own info-bar height
            project['footer_detection'] = dict(bottom=bottom, detected=bottom < project['height'])
            project['config']['analysis_bottom'] = min(project['config']['analysis_bottom'], bottom) if project.get('runs') or project.get('seed') else bottom
            if bottom < project['height']:
                try:
                    project['scale_detection'] = detect_scale_bar(gray, bottom, 1)
                    if not project['config'].get('scale_pixels'):
                        project['config']['scale_pixels'] = project['scale_detection']['length_pixels']
                except ValueError:
                    pass
            if header.get('um_per_pixel') and not project.get('runs') and not project.get('seed'):
                # Scale from the microscope's pixel size: the fields are filled in, the user only checks them.
                pixels = project['config'].get('scale_pixels') or 100
                label = pixels*header['um_per_pixel']
                nice = min((m*10.**e for e in range(-3, 5) for m in (1, 2, 5)), key=lambda v: abs(v-label))
                if abs(nice-label) <= .02*label: label, pixels = nice, nice/header['um_per_pixel']   # the bar's printed value (e.g. 200 µm); pixels follow the file's exact pixel size
                project['config'].update(scale_pixels=round(pixels, 2), scale_um=round(label, 4), calibrated=True)
                project['scale_metadata'] = dict(um_per_pixel=header['um_per_pixel'], source='TIFF header (TESCAN PixelSizeX)',
                    label_um=project['config']['scale_um'], length_pixels=project['config']['scale_pixels'])   # kept apart from config: a later run cannot lose it
            self.persist(project)
        result = super().inspect(project_id)
        if (self.root/project_id/'input/display.png').exists():
            result['preview_url'] = f'/project-files/{project_id}/input/display.png'
        return result

    def validate_config(self, project, payload):
        mode = payload.get('workspace_mode', 'labeling')
        if mode not in ('labeling', 'report'): raise ValueError('Choose labeling or report mode.')
        calibrated = payload.get('calibrated', False)
        if type(calibrated) is not bool: raise ValueError('Invalid calibration option.')
        prepared = dict(payload)
        if mode == 'report':
            prepared.update(normalize_enabled=False, background_strength=0,
                blur_method='none', blur_strength=0, preprocessing_mode='adjustable',
                min_contrast=0, min_area_pixels=1, points_per_side=16)
        # Enforce the detected boundary even for older setup forms/projects.
        self.inspect(project['id'])
        bottom = self.projects[project['id']]['footer_detection']['bottom']
        prepared['analysis_bottom'] = min(float(prepared.get('analysis_bottom', bottom)), bottom)
        if not calibrated:
            prepared.update(scale_um=1., scale_pixels=1., scale_confirmed=True)
        values = super().validate_config(project, prepared)
        factor = payload.get('scale_factor', 1.) if calibrated else 1.
        if isinstance(factor, bool) or not isinstance(factor, (int, float)) or not math.isfinite(factor) or not .01 <= factor <= 100:
            raise ValueError('Correction factor must be a number from 0.01 to 100.')
        values.update(workspace_mode=mode, calibrated=calibrated, scale_factor=float(factor))
        if calibrated: (self.root/'scale_factor.json').write_text(json.dumps(dict(scale_factor=float(factor))), encoding='utf-8')
        return values

    def run(self, job_id, project, config, run_id, number):
        folder = self.root/project['id']/'runs'/run_id
        try:
            with self.editor.lock:
                self.check_cancel(job_id)
                device = self.editor.device
                source = (self.root/project['id']/'input/normalized.png').resolve()
                gray = np.asarray(Image.open(source))[:config['analysis_bottom']]
                rgb = np.array(Image.open(source.parent/'display.png').convert('RGB'))[:config['analysis_bottom']]
                from pore_preprocessing import prepare_image
                if config['workspace_mode'] == 'labeling' and (config.get('normalize_enabled') or config.get('background_strength') or config.get('blur_strength')):
                    processed, metadata = prepare_image(gray, self.preprocessing(project, config))
                    sam_rgb = cv2.cvtColor(processed, cv2.COLOR_GRAY2RGB)
                else:
                    sam_rgb, metadata = rgb, {'mode': 'original'}
                sam_input = folder/'images/analysis_input.png'; sam_input.parent.mkdir(exist_ok=True)
                Image.fromarray(sam_rgb).save(sam_input)
                masks = {}
                batch_size = 1 if device == 'intel-gpu' else 8
                settings = dict(points_per_side=config['points_per_side'], points_per_batch=batch_size,
                    pred_iou_thresh=.7, stability_score_thresh=.85, crop_n_layers=0,
                    min_mask_region_area=0, output_mode='binary_mask')
                if config['workspace_mode'] == 'labeling':
                    from sam2.build_sam import build_sam2
                    from segment_first_pass import ProgressGenerator
                    self.progress(job_id, 5, 'Loading official SAM 2.1 Small…')
                    model = generator = None
                    try:
                        with inference_context(device):
                            if self.editor.predictor is not None:
                                model = self.editor.predictor.model
                            else:
                                from sam_runtime import build_runtime_model
                                model = build_runtime_model(device)
                            generator = ProgressGenerator(model, **settings)
                            generator.cancel_callback = lambda: self.check_cancel(job_id)
                            generator.batch_started_callback = self.job_timings[job_id].start_detection
                            generator.progress_callback = lambda n: self.batch_progress(job_id, n, math.ceil(config['points_per_side']**2/batch_size))
                            proposals = generator.generate(sam_rgb)
                            from sam2.sam2_image_predictor import SAM2ImagePredictor
                            self.editor.predictor = SAM2ImagePredictor(model)
                            self.editor.encoded_dataset = None
                    finally:
                        del generator, model
                        release_device_cache(device)
                    self.progress(job_id, 84, 'Resolving object instances…')
                    # Smaller proposals take priority inside nested proposals. Never
                    # infer foreground from brightness or a object-specific contrast.
                    proposals = [p for p in proposals if int(p['area']) >= config['min_area_pixels']]
                    occupied = np.zeros(gray.shape, bool)
                    for proposal in sorted(proposals, key=lambda p: (p['area'], -p['predicted_iou'])):
                        self.check_cancel(job_id)
                        original = proposal['segmentation'].astype(bool)
                        # Large background/complement proposals need manual review.
                        if original.mean() > .8: continue
                        mask = original & ~occupied
                        if mask.sum() < config['min_area_pixels'] or mask.sum() < .5*original.sum(): continue
                        masks[len(masks)+1] = mask; occupied |= mask
                self.check_cancel(job_id)
                np.savez_compressed(write_artifact(folder, 'entrance_candidates.npz'), **{f'candidate_{i}':m for i,m in masks.items()})
                checkpoint = checkpoint_path().resolve()
                report = dict(image=str(source), source_name=project['name'], analysis_bottom_exclusive=config['analysis_bottom'],
                    # um_per_pixel (every reported length) includes the correction factor; image_um_per_pixel (detection sizes) does not.
                    scale=dict(label_um=config['scale_um'], length_pixels=config['scale_pixels'], um_per_pixel=config['scale_um']/config['scale_pixels']*config.get('scale_factor', 1.),
                               image_um_per_pixel=config['scale_um']/config['scale_pixels'], scale_factor=config.get('scale_factor', 1.),
                               label_source='user calibration' if config['calibrated'] else 'pixel units'),
                    measurement_unit='µm' if config['calibrated'] else 'px', workspace_mode=config['workspace_mode'],
                    rgb_image=str((source.parent/'display.png').resolve()), model='SAM 2.1 Small — official pretrained',
                    settings=settings, selection_settings=dict(method='general_sam_instances', min_area_pixels=config['min_area_pixels'], min_contrast=0),
                    checkpoint=str(checkpoint), checkpoint_sha256=self.file_digest(checkpoint), inference_device=device,
                    report_deferred=True, entrance_candidate_count=len(masks), sam_input_image=str(sam_input.resolve()),
                    preprocessing_config=self.preprocessing(project, config), preprocessing_metadata=metadata,
                    status='automatic proposals for review' if masks else 'manual prompt segmentation',
                    candidates=[dict(candidate_id=i, area=int(m.sum())) for i,m in masks.items()])
                (folder/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
                dataset = project['id']+'__'+run_id
                with self.lock:
                    self.check_cancel(job_id)
                    current = self.projects[project['id']]
                    current['config'] = config
                    current['runs'].append(dict(id=run_id, number=number, dataset=dataset, config=config))
                    self.persist(current)
                    self.jobs[job_id].update(status='complete', progress=100, message='Ready.', dataset=dataset, candidate_count=len(masks))
                    self.running = False
        except OperationCancelled:
            (folder/'report.json').unlink(missing_ok=True)
            with self.lock:
                self.jobs[job_id].update(status='cancelled', message='Analysis stopped.'); self.running = False
        except Exception as error:
            (folder/'error.txt').write_text(traceback.format_exc(), encoding='utf-8')
            with self.lock:
                self.jobs[job_id].update(status='failed', message=str(error)); self.running = False
        finally:
            with self.lock:
                if job_id in self.job_timings: self.job_timings[job_id].snapshot(self.jobs[job_id]['status'], False)

    def batch_progress(self, job_id, completed, total):
        with self.lock:
            self.job_timings[job_id].batch(completed, total)
            self.progress(job_id, min(80, 10+int(70*completed/total)), 'Finding objects with SAM 2.1…')
