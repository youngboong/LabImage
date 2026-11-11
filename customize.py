"""Apply small upstream integration changes; run once on the copied source."""
from pathlib import Path
import re

def edit(path, old, new):
    p = Path(path); text = p.read_text(encoding='utf-8')
    assert old in text, (path, old[:80])
    p.write_text(text.replace(old, new), encoding='utf-8')

edit('scripts/pore_app.py', "return Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'PoreSAM/English/outputs'", "return (Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1])/'LabImage-data/outputs'")
edit('scripts/pore_app.py', 'from pore_editor import Editor,LocalPoreServer,make_handler', 'from pore_editor import LocalPoreServer\n        from lab_editor import LabEditor as Editor, make_handler')
for path in ['scripts/pore_app.py','scripts/app_paths.py']:
    p = Path(path); text = p.read_text(encoding='utf-8').replace('PORESAM_', 'LABIMAGE_').replace('PoreSAMEnglish_', 'LabImage_').replace('PoreSAM', 'LabImage').replace('Pore Details','Object Details')
    p.write_text(text, encoding='utf-8')

edit('ui/editor.html', '<link rel="stylesheet" href="/workspace.css">', '<link rel="stylesheet" href="/workspace.css"><link rel="stylesheet" href="/labimage.css">')
edit('ui/editor.html', "if(busy||!state)return;if(e.button!==0)return;if(mode==='select')", "if(busy||!state)return;if(e.button!==0)return;if(window.handleLabPointer?.(e))return;if(mode==='select')")
edit('ui/editor.html', '<script src="/feedback.js"></script>', '<script src="/labimage.js"></script>')
edit('ui/editor.html', 'fill_holes:true', 'fill_holes:false')
edit('ui/region-queue.js', 'fill_holes:true', 'fill_holes:false')

# Keep stable DOM and Python identifiers for compatibility with report drafts.
# Rename only display text and prose, not pore_* modules or camelCase identifiers.
for folder in ['ui','scripts']:
    for p in Path(folder).glob('*'):
        if p.suffix not in ('.html','.js','.py'): continue
        text = p.read_text(encoding='utf-8')
        text = text.replace('PoreSAM', 'LabImage')
        for old,new in [('Pores','Objects'),('pores','objects'),('Pore','Object'),('pore','object')]:
            text = re.sub(r'\b'+old+r'\b',new,text)
        text = text.replace('Pore Segmentation &amp; Analysis', 'General Object Segmentation &amp; Measurement')
        p.write_text(text,encoding='utf-8')

# Avoid false ellipse definitions after changing longitudinal and transverse measures.
edit('ui/pore-columns.js', 'Major axis of the moment-equivalent ellipse.', 'Longest weighted centerline path. Cycles are cut; disconnected masks use the longest component.')
edit('ui/pore-columns.js', 'Minor axis of the moment-equivalent ellipse.', 'Minimum Feret width across the convex hull of pixel cells.')
edit('ui/editor.html', 'Length and width: moment-equivalent ellipse axes.', 'L: longest centerline path after cutting skeleton cycles. W: minimum Feret width. Disconnected masks use their longest component for L.')
edit('scripts/report_composer.py', "for key, (column, title) in METRICS.items():", "unit = state['report'].get('measurement_unit', 'µm')\n    for key, (column, title) in METRICS.items():\n        title = title.replace('µm', unit)")
edit('scripts/report_composer.py', 'assets.extend(measurement_tables(stats,rows))', "assets.extend(measurement_tables(stats,rows))\n    if unit != 'µm':\n        def convert_units(value):\n            if isinstance(value, str): return value.replace('µm', unit)\n            if isinstance(value, list): return [convert_units(v) for v in value]\n            if isinstance(value, dict): return {k:convert_units(v) for k,v in value.items()}\n            return value\n        assets = convert_units(assets)")
edit('scripts/report_composer.py', "fingerprint_assets(assets)\n    cached=dict(dataset=state['dataset']", "text = text.replace('µm', unit)\n    fingerprint_assets(assets)\n    cached=dict(dataset=state['dataset']")

edit('packaging/PoreSAM.spec', "root/'scripts/pore_app.py'", "root/'scripts/pore_app.py'")
p = Path('packaging/PoreSAM.spec'); text = p.read_text(encoding='utf-8')
text = text.replace("name='PoreSAM'", "name='LabImage'")
text = text.replace("hidden=collect_submodules('sam2')+", "hidden=collect_submodules('sam2')+['lab_editor','lab_geometry','lab_workflow','lab_export','lab_selftest','report_docx','report_hwpx','report_composer','report_workspace']+")
text = text.replace("(str(root/'ui'),'ui')", "(str(root/'ui'),'ui'),(str(root/'LICENSE'),'licenses/PoreSAM'),(str(root/'THIRD_PARTY_NOTICES.md'),'licenses')")
Path('packaging/LabImage.spec').write_text(text,encoding='utf-8')

Path('checkpoints/default_model.json').write_text('''{
  "checkpoint": "sam2.1_hiera_small.pt",
  "sha256": "6d1aa6f30de5c92224f8172114de081d104bbd23dd9dc5c58996f0cad5dc4d38",
  "source": "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt",
  "model": "Official Meta SAM 2.1 Small",
  "fine_tuned": false
}\n''',encoding='utf-8')
