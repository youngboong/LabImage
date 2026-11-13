"""In-app update. A release of youngboong/LabImage may carry a small patch zip (LabImage.exe + _internal/ui, the only files
that change between most versions); the app downloads it, a helper script swaps the files once the app has closed, and starts it again."""
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

VERSION = '0.1.4'
BASE = '0.1.3'   # last version whose _internal (libraries, models) changed: raise it together with VERSION when a full install is needed
REPO = 'youngboong/LabImage'
MAX_PATCH = 300_000_000

SCRIPT = r"""@echo off
rem Full paths: another find.exe on PATH (Git) must not be picked up.
rem %1 = process id of the running app, %2 = folder with the new files, %3 = app folder
set S=%SystemRoot%\System32
:wait
"%S%\tasklist.exe" /FI "PID eq %~1" 2>nul | "%S%\find.exe" " %~1 " >nul
if not errorlevel 1 (
  "%S%\ping.exe" -n 2 127.0.0.1 >nul
  goto wait
)
"%S%\robocopy.exe" "%~2" "%~3" /E /R:30 /W:1 >"%~2\..\update.log"
if errorlevel 8 (echo Update failed. See update.log.>"%~2\..\update.error.txt") else (del "%~2\..\update.error.txt" 2>nul)
start "" "%~3\LabImage.exe"
"""


def number(version): return tuple(int(part) for part in str(version).lstrip('v').split('.'))


def fetch(url, limit=2_000_000):
    request = urllib.request.Request(url, headers={'User-Agent': 'LabImage-update', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=30) as reply:   # Windows certificate store: works behind SSL inspection
        data = reply.read(limit+1)
    if len(data) > limit: raise ValueError('The update is larger than expected.')
    return data


def check(fetch=fetch):
    try: release = json.loads(fetch(f'https://api.github.com/repos/{REPO}/releases/latest'))
    except OSError as error: raise ValueError(f'Could not reach GitHub: {getattr(error, "reason", error)}')
    latest = str(release['tag_name']).lstrip('v')
    result = dict(current=VERSION, latest=latest, update=number(latest) > number(VERSION), page=release.get('html_url'))
    if result['update']:
        name = f'LabImage-v{latest}-patch-from-v{BASE}.zip'
        asset = next((a for a in release.get('assets', []) if a['name'] == name), None)
        result['patch'] = asset and dict(url=asset['browser_download_url'], size=asset['size'], digest=asset.get('digest'))
    return result


def stage(content, folder, digest=None):
    """Unpack a patch zip into folder/files. Only LabImage.exe and _internal/ui/* are accepted."""
    if digest and digest.startswith('sha256:') and hashlib.sha256(content).hexdigest() != digest[7:]:
        raise ValueError('The downloaded update is damaged. Try again.')
    import io, shutil
    files = Path(folder)/'files'
    shutil.rmtree(files, ignore_errors=True); files.mkdir(parents=True)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = [n for n in archive.namelist() if not n.endswith('/')]
        if 'LabImage.exe' not in names or any(n != 'LabImage.exe' and not n.startswith('_internal/ui/') or '..' in n or '\\' in n or ':' in n for n in names):
            raise ValueError('This is not a LabImage update file.')
        for name in names: archive.extract(name, files)
    return files


def write_script(folder):
    script = Path(folder)/'update.cmd'
    script.write_bytes(SCRIPT.replace('\n', '\r\n').encode('ascii'))
    return script


def install(folder, fetch=fetch):
    """Download the patch of the latest release into `folder`, then start the helper that swaps the files when this process ends."""
    if not getattr(sys, 'frozen', False): raise ValueError('Updates work in the installed app.')
    found = check(fetch)
    if not found['update']: raise ValueError('LabImage is up to date.')
    if not found.get('patch'): raise ValueError(f'Version {found["latest"]} needs a full install.')
    if found['patch']['size'] > MAX_PATCH: raise ValueError('The update is larger than expected.')
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    try: content = fetch(found['patch']['url'], MAX_PATCH)
    except OSError as error: raise ValueError(f'Could not download the update: {getattr(error, "reason", error)}')
    files = stage(content, folder, found['patch']['digest'])
    subprocess.Popen(['cmd', '/c', str(write_script(folder)), str(os.getpid()), str(files), str(Path(sys.executable).parent)],
                     creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP, close_fds=True)
    return dict(restarting=True, version=found['latest'])
