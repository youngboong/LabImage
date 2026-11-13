# Build on Windows: python -m PyInstaller packaging/PoreSAM.spec --noconfirm
from pathlib import Path
import os
import json
import torch
from PyInstaller.utils.hooks import collect_data_files,collect_submodules,copy_metadata,collect_dynamic_libs
root=Path(SPECPATH).parent
if torch.version.cuda is not None:raise SystemExit('Build in the CPU-only pore-app-cpu environment; see DESKTOP.md.')
os.environ['MPLCONFIGDIR']=str(root/'build/matplotlib-cache')
manifest=root/'checkpoints/default_model.json'
name=json.loads(manifest.read_text(encoding='utf-8'))['checkpoint'] if manifest.is_file() else 'sam2.1_hiera_small.pt'
if not isinstance(name,str) or Path(name).name!=name or not name.endswith('.pt'):raise SystemExit('Invalid default checkpoint filename.')
weights=root/'checkpoints'/name
if not weights.is_file():raise SystemExit('Place SAM 2.1 Small at '+str(weights))
datas=[(str(root/'ui'),'ui'),(str(root/'LICENSE'),'licenses/PoreSAM'),(str(root/'THIRD_PARTY_NOTICES.md'),'licenses'),(str(weights),'checkpoints')]
if manifest.is_file():datas.append((str(manifest),'checkpoints'))
datas += [(str(root/'vendor/sam2/LICENSE'),'licenses/SAM2'), (str(root/'vendor/sam2/LICENSE_cctorch'),'licenses/SAM2')]
datas+=collect_data_files('sam2')+copy_metadata('SAM-2')
datas += [(str(f), 'checkpoints/openvino') for f in (root/'checkpoints/openvino').iterdir() if not f.name.startswith('cnt_')]   # SAM encoder/decoder; no tube model
datas += collect_data_files('openvino', includes=['libs/*.xml','libs/*.json']) + copy_metadata('openvino')
import importlib.metadata
ov_license = Path(importlib.metadata.distribution('openvino').locate_file('openvino-2025.4.0.dist-info/licenses'))
datas += [(str(ov_license), 'licenses/OpenVINO')]
gpu_binaries = collect_dynamic_libs('openvino')
hidden=collect_submodules('sam2')+['lab_editor','lab_geometry','particle_detect','app_update','lab_workflow','lab_export','lab_selftest','lab_ui_smoke','report_docx','report_hwpx','report_composer','report_workspace']+['automate_pores','report_bundle','pore_details_export','app_paths','matplotlib.backends.backend_pdf','matplotlib.backends.backend_svg','matplotlib.backends.backend_agg']
hidden += ['lab_openvino'] + collect_submodules('openvino.properties')
a=Analysis([str(root/'scripts/pore_app.py')],pathex=[str(root/'scripts')],binaries=gpu_binaries,datas=datas,hiddenimports=hidden,
           hooksconfig={'matplotlib':{'backends':['Agg','pdf','svg']}},
           excludes=['IPython','ipykernel','jupyter','notebook','PyQt5','PyQt6','PySide2','PySide6','playwright','pytest','tensorboard','tkinter','_tkinter'],noarchive=False)
# Library examples, benchmarks and development tools are not application data.
def runtime_data(entry):
    name=entry[0].replace('\\','/').lower()
    unused=('matplotlib/mpl-data/sample_data/','torch/fx/passes/tests/',
            'torch/testing/_internal/distributed/rpc/examples/',
            'torch/utils/benchmark/examples/','torch/_export/db/examples/')
    return not (name.startswith(unused) or name in ('torch/bin/protoc.exe','sam2/benchmark.py')
                or name.endswith('/readme.txt'))
a.datas=[entry for entry in a.datas if runtime_data(entry)]
a.binaries=[entry for entry in a.binaries if runtime_data(entry)]
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='LabImage',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=bool(os.environ.get('LABIMAGE_CONSOLE')))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='LabImage')
