"""Check real source dimensions and zero footer labels in an isolated project."""
from pathlib import Path
import json
import time
import numpy as np
from PIL import Image
from lab_editor import LabEditor
from lab_export import export_images

root=Path(__file__).resolve().parents[1]
destination=root/'validation/footer-export'
editor=LabEditor(output_root=destination/'edits',project_root=destination/'projects',device='cpu')
source=root/'LabImage-data/outputs/projects/image_30a3f4cab6b595f9/input/normalized.png'
p=editor.workflow.upload('sem.png',source.read_bytes())
assert p['config']['analysis_bottom']==768
config=dict(p['config'],workspace_mode='report',calibrated=False,analysis_bottom=888)
job=editor.workflow.start(p['id'],config)
for _ in range(200):
    status=editor.workflow.status(job['job_id'])
    if status['status']=='complete':break
    assert status['status']!='failed',status
    time.sleep(.05)
assert status['status']=='complete'
state=editor.state(status['dataset'])
assert state['gray'].shape==(768,1024)
assert state['sam_rgb'].shape[:2]==(768,1024)
state['report']['workspace_mode']='labeling'
mask=np.zeros((768,1024),bool);mask[700:768,100:150]=True
editor.save(state,{300:mask},{},[],301,dict(type='test'))
folder=Path(export_images(editor,state,dict(directory=str(destination/'exports'))))
labels=np.asarray(Image.open(folder/'instances.png'))
assert labels.shape==(888,1024) and not labels[768:].any()
assert np.all(labels[700:768,100:150]==300)
summary=dict(passed=True,source_size=[1024,888],analysis_size=[1024,768],excluded_rows=120,
    exported_labels_shape=list(labels.shape),excluded_labels_zero=True)
(destination/'result.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary))
