"""Exercise real pretrained inference, immutable edits, labels and reports."""
import base64
import io
import json
import os
from pathlib import Path
import time
import zipfile
import cv2
import numpy as np
from PIL import Image


def run(destination, device='cpu'):
    destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=True)
    os.environ['LABIMAGE_DATA_DIR']=str(destination/'data')
    from lab_editor import LabEditor
    from lab_export import export_images
    from app_paths import checkpoint_path
    import hashlib
    digest=hashlib.sha256(checkpoint_path().read_bytes()).hexdigest()
    assert digest=='6d1aa6f30de5c92224f8172114de081d104bbd23dd9dc5c58996f0cad5dc4d38',digest
    editor=LabEditor(output_root=destination/'data/manual_edits',project_root=destination/'data/projects',device=device)
    rgb=np.full((256,320,3),35,np.uint8)
    cv2.circle(rgb,(90,100),42,(200,190,160),-1)
    cv2.rectangle(rgb,(185,60),(265,155),(100,180,205),-1)
    cv2.ellipse(rgb,(160,200),(80,25),0,0,180,(170,170,170),8)
    buffer=io.BytesIO();Image.fromarray(rgb).save(buffer,format='PNG')
    (destination/'sample.png').write_bytes(buffer.getvalue())
    project=editor.workflow.upload('sample.png',buffer.getvalue())
    def start(mode,calibrated=False):
        config=dict(project['config'],workspace_mode=mode,calibrated=calibrated,scale_confirmed=True,scale_um=10.,scale_pixels=100.)
        job=editor.workflow.start(project['id'],config)
        deadline=time.monotonic()+300
        while time.monotonic()<deadline:
            status=editor.workflow.status(job['job_id'])
            if status['status']=='complete': return editor.state(status['dataset'])
            if status['status']=='failed': raise RuntimeError(status['message'])
            time.sleep(.25)
        raise RuntimeError('Inference timed out')
    report=start('report',True)
    assert not report['masks'] and editor.predictor is None, 'Report mode must never auto-segment'
    preview=editor.quick_segment(report,dict(dataset=report['dataset'],revision=report['revision'],points=[[90,100]],labels=[1],target_id=None))
    assert preview['choices'] and all(m.any() for m in report['preview']['masks'])
    applied=editor.mutate(report,dict(revision=report['revision'],token=preview['token'],choice=0,target_id=None),'apply')
    assert len(report['masks'])==1
    baseline=report['revision']
    editor.mutate(report,dict(revision=report['revision'],target_ids=list(report['masks'])),'delete')
    assert not report['masks']
    editor.mutate(report,dict(revision=report['revision']),'undo')
    assert len(report['masks'])==1 and report['revision']>baseline
    identifier=next(iter(report['masks']))
    editor.manual_measurement(report,dict(object_id=identifier,axis='length',points=[[60,100],[90,70],[120,100]]))
    editor.manual_measurement(report,dict(object_id=identifier,axis='width',points=[[90,80],[90,120]]))
    measured=editor.measurements(report)['candidates'][0]
    scale=report['report']['scale']['um_per_pixel']
    assert abs(measured['length_um']-np.sqrt(1800)*2*scale)<1e-6
    assert abs(measured['width_um']-40*scale)<1e-6
    editor.mutate(report,dict(revision=report['revision']),'undo')
    assert editor.measurements(report)['candidates'][0]['width_um'] is None
    editor.manual_measurement(report,dict(object_id=identifier,axis='width',points=[[90,80],[90,120]]))
    figure_folder=Path(export_images(editor,report,dict(directory=str(destination/'exports'),opacity=18,labels=True)))
    assert (figure_folder/'measurements.png').is_file()
    from report_composer import content,defaults,export
    data=content(editor,report);options=defaults(data)
    options.update(title='LabImage validation',file_name='LabImage_validation',items=[dict(id='comparison',selected=True,caption='Measured objects')])
    report_folder=Path(export(editor,report,str(destination/'reports'),options))
    assert (report_folder/'LabImage_validation.pdf').read_bytes().startswith(b'%PDF')
    for ext in ['docx','hwpx']:
        with zipfile.ZipFile(report_folder/f'LabImage_validation.{ext}') as archive:
            assert archive.testzip() is None
    label_state=start('labeling')
    automatic_count=len(label_state['masks'])
    assert automatic_count>0,'Official SAM must return candidates on the test scene'
    # A sparse ID above 255, holes and original source dimensions must survive.
    masks={1:np.zeros((256,320),bool),300:np.zeros((256,320),bool)}
    masks[1][20:60,20:60]=True;masks[1][30:40,30:40]=False
    masks[300][90:140,190:260]=True
    editor.save(label_state,masks,{},label_state['history']+[label_state['revision']],301,dict(type='selftest'))
    label_folder=Path(export_images(editor,label_state,dict(directory=str(destination/'exports'))))
    with Image.open(label_folder/'instances.png') as im: saved=np.asarray(im)
    assert set(np.unique(saved))=={0,1,300}
    assert saved[35,35]==0 and saved[110,220]==300
    assert saved.shape==(256,320)
    assert np.array_equal(np.load(label_folder/'instances.npy'),saved)
    assert not list(label_folder.glob('*.pdf'))
    # Reopening must retain revisions and the original RGB image.
    reopened=LabEditor(output_root=destination/'data/manual_edits',project_root=destination/'data/projects',device=device)
    restored=reopened.state(label_state['dataset'])
    assert restored['revision']==label_state['revision'] and set(restored['masks'])=={1,300}
    assert np.array_equal(restored['rgb'],rgb)
    gpu_recovery = None
    if device == 'intel-gpu':
        model = editor.predictor.model
        assert model.intel_gpu_info['active_device']=='intel-gpu',model.intel_gpu_info
        # Exercise the real worker error/exit path, without triggering a driver bug.
        client = model._intel_gpu_worker
        try:
            client.infer('_validation_failure', [])
            raise AssertionError('Worker fault was not reported')
        except RuntimeError:
            pass
        before_revision = label_state['revision']
        preserved = label_state['masks'][1].copy()
        result = editor.quick_segment(label_state,dict(revision=before_revision,
            points=[[220,110]],labels=[1],target_id=300,auto_apply=True))
        assert result['applied'] and result['inference_device']=='cpu' and result['runtime_notice']
        assert label_state['revision']>before_revision
        assert np.array_equal(label_state['masks'][1],preserved)
        retry = reopened.snapshot(label_state,label_state['revision'])
        assert set(retry['masks'])=={1,300}
        gpu_recovery = dict(worker_error_exits=True,failed_request_retried_on_cpu=True,
            revision_committed=True,other_instances_preserved=True)
    summary=dict(passed=True,device=editor.device,gpu_info=getattr(editor.predictor.model,'intel_gpu_info',None),model_sha256=digest,automatic_candidates=automatic_count,
        report_mode_automatic_masks=0,real_point_inference=True,undo_and_reopen=True,
        gpu_recovery=gpu_recovery,instance_ids=[0,1,300],instance_holes_preserved=True,rgb_preserved=True,
        report_formats=['pdf','hwpx','docx'],report_directory=str(report_folder),label_directory=str(label_folder))
    (destination/'selftest.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary


if __name__=='__main__':
    import sys
    print(json.dumps(run(sys.argv[1] if len(sys.argv)>1 else 'validation/backend'),indent=2))
