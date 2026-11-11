# LabImage

Windows에서 실행하는 일반 객체 분할·측정 앱입니다. PoreSAM의 편집 이력과
보고서 작성 방식을 바탕으로 라벨링과 일반 보고서 작업을 분리했습니다.

## 실행

이 폴더의 **LabImage.exe**를 실행하세요. 옆의 **_internal** 폴더도 함께
있어야 합니다. Python을 따로 설치하지 않아도 됩니다. 작업 내용과 로그는
`LabImage-data`에 저장됩니다. 여러 창을 열면 작업 공간이 분리됩니다.

모델은 Meta 공식 **SAM 2.1 Small 원본 사전학습 가중치**이며, 기공 또는
사용자 이미지로 추가 파인튜닝하지 않았습니다. CPU로 실행합니다.

## 라벨링

1. 시작 화면에서 **라벨링**을 선택하고 이미지를 불러옵니다.
2. 분석 영역·최소 면적·샘플링을 설정하고 **자동 분석 시작**을 누릅니다.
   스케일 보정은 선택 사항입니다.
3. 객체 내부에 점을 찍으면 SAM 결과가 바로 반영됩니다. 기존 객체 내부를
   클릭하면 해당 객체를 수정합니다. 다른 객체의 픽셀은 보존합니다.
4. **Shift+클릭**은 같은 객체에 양성 점을 추가합니다. **우클릭** 또는
   **점 −**는 제외할 점입니다. **새 객체**로 프롬프트를 초기화합니다.
5. 결과를 먼저 검토하려면 **클릭 즉시 마스크 반영**을 끄세요. 후보를
   선택하고 **Enter / Add Object**로 반영합니다.
6. 점만으로 어려운 객체에는 **박스 (보조)**를 직접 지정하고 Preview를
   누르세요. 보조 도구에서 다각형·타원·잘라내기를 사용할 수 있습니다.
7. **Select**에서 객체를 선택하고 삭제·병합할 수 있습니다.
   **Ctrl+Z**는 프롬프트 또는 저장된 수정을 되돌립니다.
8. **Save Images · 인스턴스 마스크**로 저장합니다. 보고서는 생성하지 않습니다.

저장 폴더는 기존 파일을 덮어쓰지 않는 고유 이름으로 생성됩니다.

| 파일 | 내용 |
| --- | --- |
| `image.png` | 마스크와 좌표가 일치하는 RGB 8비트 이미지 |
| `instances.png` | 16비트 정수 인스턴스 맵. 배경=0, 객체=고유 ID |
| `instances.npy` | 같은 인스턴스 맵의 NumPy 배열 |
| `instances_preview.png` | 사람이 확인하기 위한 색상 미리보기 |
| `instances.json` | ID·면적·박스·프롬프트·모델 출처 |
| `original.*` | 불러온 원본 파일 그대로 |

색상 미리보기는 학습용 라벨 맵이 아닙니다. `instances.png`를 회색 영상으로
8비트 변환하지 마세요. ID는 삭제 이력 때문에 연속되지 않을 수 있으며
최대 65535입니다. 분석 영역 밖은 0으로 저장됩니다. 16비트 원본은
학습용 `image.png`에 정규화되며 `original.*`에는 원본이 보존됩니다.

## Report workspace (English UI)

Report mode uses the original image, with no preprocessing or automatic analysis.

1. Choose Report, load an image, optionally calibrate, and open the segmentation workspace.
2. Segment an object with point prompts and apply it.
3. In Manual measurements, choose the object and L (longitudinal) or W (transverse).
4. Follow object (2 points): click the start and end on the object, then Save path. The app traces the shortest 8-connected path inside its mask and measures that full path. Points snap to object pixels within 5 pixels. Disconnected endpoints are rejected.
5. Review the yellow route. To replace it, use Draw curve (drag) or Click curve points (successive clicks), then Save path. Drawn paths follow your input, may extend outside the mask, and sum all segment lengths without smoothing.
6. Repeat for the other axis. L/W is the aspect ratio. Unmeasured values remain blank. Undo point edits the draft; Cancel discards it; Ctrl+Z undoes a saved change.
7. Save Images exports the annotated figure, CSV and JSON including paths. Generate Report retains PDF, HWPX and Word export using the same measurements.

Measurements apply to any segmented object. Area and perimeter come from the mask. Boundary objects are excluded from size statistics.

## Measurement method

Two endpoints follow the selected mask, not a straight chord through the background. Both L and W support object-following and manually drawn paths. Labeling remains a separate automatic-segmentation and instance-mask export workflow.

## Build

Use `.venv/Scripts/python.exe -m PyInstaller packaging/LabImage.spec --workpath build/labimage --noconfirm`. Distribute LabImage.exe together with its _internal directory.

## Endpoint measurements and outside labels

Automatic center/L/W measurements are disabled. Select each axis and its two endpoints; Save path measures the curve inside the mask. Direct curve drawing remains available. Numeric values are placed outside the object with leader lines. Perpendicular end caps remain. Clear saved measurements removes both axes; Ctrl+Z restores them.

## Center waypoint and end caps

The center point is automatic and visible before measurements. Both user-selected endpoints connect to this same center through the mask. L/W endpoints remain manual. Existing endpoint measurements use their saved ends with the center waypoint. Drawn curves retain the exact user path. End caps have a longer minimum length and extend across the local object section when wider.

## Intel GPU runtime

The app now defaults to auto device selection, preferring Intel GPU through OpenVINO when available. The official SAM 2.1 Small encoder and mask decoder execute on GPU; prompt preparation and file operations remain on CPU. The header identifies the active engine. First use compiles and caches GPU kernels and may take longer. Use --device intel-gpu to require GPU, or --device cpu to use CPU explicitly. GPU models are converted from the unchanged official checkpoint using FP16 weight storage. No fine-tuning is performed. Immediate labeling now skips redundant preview images and applies edits in one request.

## 입자·튜브 측정 (Report)

Set up의 **Sample**에서 대상을 고릅니다.

- **Particles**: 보정을 확인하면 입자를 자동으로 찾습니다. 왼쪽 원본, 오른쪽 선택된
  입자 화면에서 클릭·Shift+클릭으로 고르고 Delete로 지우거나, 빈 입자를 클릭해
  추가합니다. 다음 화면에서 길이(가장 긴 Feret 직경)와 너비(길이에 수직인 방향의
  Feret 직경) 선을 고치고, Details에서 분포를 봅니다.
- **Tubes (CNT)**: Tube 도구로 양 끝을 클릭해 곡선 길이를 재거나(Auto), 클릭한 점을
  직선으로 잇습니다(Manual). 너비는 한쪽 가장자리 선과 반대쪽 클릭으로 잽니다.

TESCAN TIFF는 파일에 든 픽셀 크기로 스케일이 자동 입력됩니다. **Save image**는 원본
폴더에 `이름(2)`(길이)와 `이름(3)`(너비) 그림과 CSV를 저장합니다.

## 소스에서 실행

모델(`checkpoints/`)과 SAM 2 코드(`vendor/sam2`)는 저장소에 없습니다. 배포본 zip에는
들어 있습니다.
