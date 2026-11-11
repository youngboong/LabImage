import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import numpy as np


def test_measurements_flag_tube_objects(tmp_path):
    from lab_editor import LabEditor
    editor = LabEditor(output_root=tmp_path/'edits', project_root=tmp_path/'projects', device='cpu')
    gray = np.full((120, 120), 90, np.uint8)
    masks = {1: np.zeros(gray.shape, bool), 2: np.zeros(gray.shape, bool)}
    masks[1][20:40, 20:80] = True
    masks[2][60:100, 20:50] = True
    state = dict(dataset='t', gray=gray, masks=masks, history=[], next_id=3, revision=0,
        report=dict(workspace_mode='report', image='x.png', scale=dict(um_per_pixel=.27), measurement_unit='µm'),
        annotations={'1': dict(source='prompted_sam', tube=dict(version=1)), '2': dict(source='prompted_sam')})
    flags = {r['candidate_id']: r['tube'] for r in editor.measurements(state)['candidates']}
    assert flags == {1: True, 2: False}
