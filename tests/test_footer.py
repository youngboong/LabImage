import io
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import cv2
import numpy as np
from PIL import Image
from lab_footer import detect_information_footer
from lab_editor import LabEditor


def scene(background=45):
    rng=np.random.default_rng(32)
    gray=rng.integers(30,210,(320,512),dtype=np.uint8)
    gray[256:]=background
    ink=255 if background<128 else 0
    cv2.line(gray,(250,256),(250,319),ink,1)
    cv2.putText(gray,'SEM  WD: 8.5 mm',(10,280),cv2.FONT_HERSHEY_SIMPLEX,.5,ink,1)
    cv2.putText(gray,'MAG: 30 kx  5 kV',(10,307),cv2.FONT_HERSHEY_SIMPLEX,.5,ink,1)
    return gray


def test_footer_with_rules_dark_and_light():
    for background in [0,45,255]:
        assert detect_information_footer(scene(background))==256


def test_no_footer_preserves_image():
    a=scene();a[256:]=45
    assert detect_information_footer(a)==320
    assert detect_information_footer(a[:256])==256


def test_upload_and_both_modes_enforce_footer(tmp_path):
    editor=LabEditor(output_root=tmp_path/'edits',project_root=tmp_path/'projects',device='cpu')
    buf=io.BytesIO();Image.fromarray(scene()).save(buf,format='PNG')
    p=editor.workflow.upload('sem.png',buf.getvalue())
    assert p['footer_detection']==dict(bottom=256,detected=True)
    assert p['config']['analysis_bottom']==256
    for mode in ['report','labeling']:
        config=editor.workflow.validate_config(editor.workflow.projects[p['id']],dict(p['config'],
            workspace_mode=mode,calibrated=False,analysis_bottom=320))
        assert config['analysis_bottom']==256
    buf=io.BytesIO();Image.fromarray(scene()[:256]).save(buf,format='PNG')
    normal=editor.workflow.upload('normal.png',buf.getvalue())
    assert normal['config']['analysis_bottom']==256
    assert not normal['footer_detection']['detected']


def test_smooth_substrate_above_the_bar():
    # dark, nearly flat image area (std ~5) and a uniform first bar row: the row that differs from the image is the boundary
    a=scene(45)
    a[:256]=np.random.default_rng(1).normal(57,5,(256,512)).clip(0,255).astype(np.uint8)
    a[256]=99
    assert detect_information_footer(a)==256


def test_scale_and_info_bar_from_the_tescan_header(tmp_path):
    from pathlib import Path
    import pytest
    source = Path(__file__).resolve().parents[1]/'261110_704113_powder/SWCNT_704113_300x_3.tif'
    if not source.exists(): pytest.skip('sample image not in this checkout')
    from lab_editor import LabEditor
    from lab_workflow import tescan_header
    header = tescan_header(source)
    assert abs(header['um_per_pixel']-.9089) < 1e-3 and header['strip'] == 178
    editor = LabEditor(output_root=tmp_path/'edits', project_root=tmp_path/'projects', device='cpu')
    project = editor.workflow.upload(source.name, source.read_bytes())
    config = project['config']
    assert config['calibrated'] is True and config['scale_um'] == 200 and abs(config['scale_um']/config['scale_pixels']-.9089) < 2e-3   # the bar's printed 200 µm
    assert project['footer_detection']['bottom'] == 768 and project['scale_metadata']['um_per_pixel'] == header['um_per_pixel']
    assert tescan_header(tmp_path/'missing.tif') == {}


def test_source_path_is_remembered_on_a_fresh_install(tmp_path):
    from lab_editor import LabEditor
    editor = LabEditor(output_root=tmp_path/'not'/'there'/'yet', project_root=tmp_path/'projects', device='cpu')
    editor.remember_source('abc', tmp_path/'image.tif')   # used to fail: the edits folder does not exist before the first save
    assert editor.source_paths() == {'abc': str(tmp_path/'image.tif')}


def test_replace_file_waits_out_a_short_windows_lock(tmp_path, monkeypatch):
    from pathlib import Path
    import pytest
    from result_paths import replace_file
    source, target = tmp_path/'a.pending', tmp_path/'a.json'
    source.write_text('new'); target.write_text('old')
    real, calls = Path.replace, []
    def flaky(self, other):
        calls.append(1)
        if len(calls) < 3: raise PermissionError(13, 'Access is denied')   # WinError 5 while another program reads the file
        return real(self, other)
    monkeypatch.setattr(Path, 'replace', flaky)
    replace_file(source, target)
    assert target.read_text() == 'new' and len(calls) == 3
    monkeypatch.setattr(Path, 'replace', lambda self, other: (_ for _ in ()).throw(PermissionError(13, 'locked')))
    with pytest.raises(PermissionError): replace_file(tmp_path/'b', tmp_path/'c', tries=2)   # a real, lasting denial still surfaces
