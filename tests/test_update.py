import io, json, subprocess, sys, zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import app_update


def patch_zip(names):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as archive:
        for name in names: archive.writestr(name, 'new '+name)
    return data.getvalue()


def release(tag, assets=()):
    return lambda url, limit=0: json.dumps(dict(tag_name=tag, html_url='page', assets=[dict(name=n, browser_download_url='u', size=5) for n in assets])).encode()


def test_check_compares_versions_and_finds_the_patch_for_this_base(monkeypatch):
    monkeypatch.setattr(app_update, 'VERSION', '0.1.9'); monkeypatch.setattr(app_update, 'BASE', '0.1.3')
    assert app_update.check(release('v0.1.9'))['update'] is False
    assert app_update.check(release('v0.1.10', ['LabImage-v0.1.10-patch-from-v0.1.3.zip']))['patch']['size'] == 5   # 10 > 9, not text order
    assert app_update.check(release('v0.2.0', ['LabImage-v0.2.0-patch-from-v0.2.0.zip', 'LabImage-v0.2.0-win64.zip']))['patch'] is None   # full install


def test_stage_accepts_only_app_files(tmp_path):
    files = app_update.stage(patch_zip(['LabImage.exe', '_internal/ui/labimage.js']), tmp_path)
    assert (files/'_internal/ui/labimage.js').read_text() == 'new _internal/ui/labimage.js'
    for bad in (['_internal/ui/a.js'], ['LabImage.exe', '_internal/torch/x.dll'], ['LabImage.exe', '_internal/ui/../../x']):
        with pytest.raises(ValueError): app_update.stage(patch_zip(bad), tmp_path)
    with pytest.raises(ValueError, match='damaged'): app_update.stage(patch_zip(['LabImage.exe']), tmp_path, 'sha256:'+'0'*64)


@pytest.mark.skipif(sys.platform != 'win32', reason='helper is a Windows script')
def test_helper_swaps_files_after_the_app_ended(tmp_path):
    app = tmp_path/'app folder'; (app/'_internal/ui').mkdir(parents=True)
    (app/'LabImage.exe').write_text('old'); (app/'_internal/ui/keep.css').write_text('kept')
    files = app_update.stage(patch_zip(['LabImage.exe', '_internal/ui/labimage.js']), tmp_path/'update')
    script = tmp_path/'update/update.cmd'; script.write_bytes(app_update.SCRIPT.replace('start ""', 'rem start').replace(chr(10), chr(13)+chr(10)).encode('ascii'))
    ended = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(4)'])   # the app, still open
    subprocess.run(['cmd', '/c', str(script), str(ended.pid), str(files), str(app)], timeout=60)
    assert ended.poll() is not None   # the helper waited for the app to end
    assert (app/'LabImage.exe').read_text() == 'new LabImage.exe' and (app/'_internal/ui/labimage.js').exists()
    assert (app/'_internal/ui/keep.css').read_text() == 'kept' and not (tmp_path/'update/update.error.txt').exists()
