"""Lossless instance labels for training; annotated figures for reports."""
import colorsys
import csv
import json
import shutil
from pathlib import Path
import numpy as np
from PIL import Image
from report_bundle import export_paths, source_image
from lab_geometry import measured_overlay


def export_images(editor, state, payload):
    mode = state['report'].get('workspace_mode', 'report')
    staging, destination = export_paths(editor, state, payload.get('directory'), 'instances' if mode == 'labeling' else 'figures')
    try:
        raw_source = None
        for project in editor.workflow.projects.values():
            if any(r['dataset'] == state['dataset'] for r in project['runs']):
                raw_source = editor.workflow.root/project['id']/project['original_file']; break
        if raw_source: shutil.copyfile(raw_source, staging/('original'+raw_source.suffix.lower()))
        unit = state['report'].get('measurement_unit', 'µm')
        if mode == 'labeling':
            # Full source dimensions; pixels outside the analysis ROI stay 0.
            full_height = np.asarray(Image.open(state['report']['image'])).shape[0]
            max_id = max(state['masks'], default=0)
            if max_id > np.iinfo(np.uint16).max:
                raise ValueError('16-bit PNG supports IDs 1–65535. Start a new labeling session.')
            labels = np.zeros((full_height,state['gray'].shape[1]), np.uint16)
            preview = np.zeros((*labels.shape,3), np.uint8)
            objects = []
            for identifier, mask in sorted(state['masks'].items()):
                if (labels[:mask.shape[0]][mask] != 0).any(): raise ValueError('Overlapping instance labels.')
                labels[:mask.shape[0]][mask] = identifier
                color = np.array(colorsys.hsv_to_rgb((identifier*.61803398875)%1, .75, 1))*255
                preview[:mask.shape[0]][mask] = color.astype(np.uint8)
                yy,xx = np.nonzero(mask)
                objects.append(dict(id=identifier, area_pixels=int(mask.sum()), bbox_xywh=[int(xx.min()),int(yy.min()),int(xx.max()-xx.min()+1),int(yy.max()-yy.min()+1)],
                    annotation=state['annotations'].get(str(identifier),{})))
            Image.fromarray(labels).save(staging/'instances.png')
            Image.fromarray(preview).save(staging/'instances_preview.png')
            np.save(staging/'instances.npy', labels, allow_pickle=False)
            # This image is paired pixel-for-pixel with the instance label map.
            display = Path(state['report']['rgb_image'])
            shutil.copyfile(display, staging/'image.png')
            metadata = dict(format='LabImage instance labels v1', background_id=0, dtype='uint16',
                width=labels.shape[1], height=labels.shape[0], analysis_bottom=state['gray'].shape[0],
                instances=objects, instance_count=len(objects), dataset=state['dataset'], revision=state['revision'],
                model=state['report']['model'], checkpoint_sha256=state['report']['checkpoint_sha256'],
                source_name=state['report']['source_name'], training_status='user corrections; review before training')
            (staging/'instances.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        else:
            figure = measured_overlay(state, opacity=float(payload.get('opacity',18))/100,
                show_length=payload.get('show_length',True), show_width=payload.get('show_width',True),
                show_ids=payload.get('labels',True), font_size=int(payload.get('font_size',16)))
            figure.save(staging/'measurements.png')
            if any('tube' in a or 'particle' in a for a in state.get('annotations', {}).values()):
                # Hand-labelled CNT figures keep lengths (T#) and widths (D#) on separate images.
                common = dict(opacity=float(payload.get('opacity',18))/100, show_ids=payload.get('labels',True), font_size=int(payload.get('font_size',16)))
                measured_overlay(state, show_length=True, show_width=False, **common).save(staging/'measurements_T.png')
                measured_overlay(state, show_length=False, show_width=True, **common).save(staging/'measurements_D.png')
            original = Image.fromarray(state['rgb'])
            comparison = Image.new('RGB',(figure.width*2,figure.height))
            comparison.paste(original,(0,0)); comparison.paste(figure,(figure.width,0))
            comparison.save(staging/'comparison.png')
            from analyze_candidates import measure_masks
            table, stats, *_ = measure_masks(sorted(state['masks'].items()), state['gray'].shape,
                state['report']['scale']['um_per_pixel'], gray=state['gray'], manual=state.get('annotations', {}) if state['report'].get('workspace_mode') == 'report' else None)
            table.rename(columns={'length_um':f'curve_length_{unit}','width_um':f'transverse_path_length_{unit}', 'area_um2':f'area_{unit}2','perimeter_um':f'perimeter_{unit}'}).to_csv(staging/'measurements.csv',index=False,encoding='utf-8-sig')
            stats.update(measurement_unit=unit, model=state['report']['model'], checkpoint_sha256=state['report']['checkpoint_sha256'])
            from lab_geometry import report_geometry
            stats['measurement_paths'] = {}
            for i, mask in state['masks'].items():
                annotation = state['annotations'].get(str(i), {})
                g = report_geometry(mask, annotation)
                stats['measurement_paths'][str(i)] = dict(center=g.get('center_point'),
                    paths=dict(length=g['length_path'], width=g['width_line']), tube=annotation.get('tube'),
                    methods=dict(length=annotation.get('measurement_methods', {}).get('length', g['length_method']),
                        width=annotation.get('measurement_methods', {}).get('width', 'unmeasured')))
            (staging/'measurements.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2),encoding='utf-8')
        staging.rename(destination)
        return str(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
