"""Start destination selection beside the previous folder, rather than inside it."""
import json
import os
from pathlib import Path


def documents_directory():
    """Use the Windows Documents folder, including redirected/OneDrive locations."""
    if os.name=='nt':
        import ctypes
        buffer=ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None,5,None,0,buffer)==0 and buffer.value:
            return Path(buffer.value)
    return Path.home()/'Documents'


class ExportFolderPicker:
    def __init__(self, choose, settings_path, fallback=None):
        self.choose = choose
        self.settings_path = Path(settings_path)
        self.fallback = Path(fallback or documents_directory())
        try:
            self.last = json.loads(self.settings_path.read_text(encoding='utf-8')).get('directory', '')
        except (OSError, ValueError, AttributeError):
            self.last = ''
        if not isinstance(self.last, str):
            self.last = ''

    def __call__(self, current_directory=''):
        current = current_directory if isinstance(current_directory, str) else ''
        previous = Path(current.strip() or self.last).expanduser() if current.strip() or self.last else None
        first_default = not self.last and previous == self.fallback
        initial = previous.parent if previous and previous.is_absolute() and not first_default else self.fallback
        while not initial.is_dir() and initial.parent != initial:
            initial = initial.parent
        result = self.choose(str(initial))
        if not result:
            return ''
        self.last = str(Path(result).expanduser())
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            pending = self.settings_path.with_suffix('.tmp')
            pending.write_text(json.dumps(dict(directory=self.last)), encoding='utf-8')
            pending.replace(self.settings_path)
        except OSError:
            pass
        return self.last
