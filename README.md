# LabImage

SEM 이미지에서 입자의 길이와 너비를 재는 Windows 앱입니다. Meta의 SAM 2.1로 입자를 찾고,
사람이 결과를 검수해 고친 뒤 그림과 CSV로 저장합니다. 이미지 전체를 객체 단위로 나누는
라벨링 작업 공간도 함께 들어 있습니다.

## 실행

배포 zip을 풀고 `LabImage\LabImage.exe`를 실행합니다. 옆의 `_internal` 폴더가 함께 있어야 하며
Python을 따로 설치할 필요는 없습니다. 작업 내용과 로그는 `LabImage-data`에 저장됩니다.

시작 화면에서 작업 공간을 고릅니다.

- Report: 입자를 찾아 길이와 너비를 재고 그림, CSV, 보고서를 만듭니다.
- Labeling: 이미지의 모든 객체를 나눠 학습용 인스턴스 마스크로 내보냅니다.

## 모델과 장치

모델은 Meta 공식 SAM 2.1 Small 사전학습 가중치이며 따로 파인튜닝하지 않았습니다.
장치는 자동으로 고릅니다. Intel GPU가 있으면 OpenVINO로 인코더와 마스크 디코더를 GPU에서
돌리고 프롬프트 준비와 파일 작업은 CPU가 맡습니다. GPU용 모델은 공식 체크포인트를 FP16으로
변환만 한 것입니다. 지금 쓰는 엔진은 헤더에 나옵니다. GPU를 처음 쓸 때는 커널을 컴파일해
캐시하느라 시간이 더 걸릴 수 있습니다. 장치를 직접 정하려면 `--device intel-gpu` 또는
`--device cpu`를 붙여 실행합니다.

## 입자 측정 (Report)

1. Load image에서 New image로 이미지를 엽니다. 이미 분석한 이미지는 Open analysis에 있습니다.
   Open analysis는 이미지를 연 폴더별로 묶어 보여 주고, 마지막으로 연 분석에 테두리를 칠합니다.
2. Set up에서 스케일을 정합니다. TESCAN TIFF는 파일에 든 픽셀 크기로 자동 입력됩니다.
   그 밖의 이미지는 Measure scale bar로 스케일 바를 재거나 µm 값을 직접 넣습니다. 필요하면 Correction factor도
   넣습니다(아래 측정 방법 참고). Confirm calibration을 체크하거나 Detect particles를 누르면 입자를 찾습니다.
3. Select particles 화면에서 왼쪽은 원본, 오른쪽은 찾은 입자입니다. 입자를 클릭해 고르고
   (Shift·Ctrl+클릭으로 여러 개) Delete로 지웁니다. 빠진 입자는 클릭하면 추가됩니다.
   Detect particles를 다시 누르면 빠진 입자를 다시 찾아 더하고 Ctrl+Z로 되돌릴 수 있습니다.
4. Next: edit lines로 넘어가 길이선과 너비선을 고칩니다. Select로 선이나 수치를 고르고
   Delete로 지우며, Draw로 Length 또는 Width 선을 새로 긋습니다. 끌거나 두 번 클릭해 긋고,
   Shift를 누르면 가로·세로·45°로 고정됩니다. 빈 배경에 그은 선은 새 입자가 되고,
   그 입자의 마지막 선을 지우면 입자도 지워집니다.
5. Details에서 입자별 표와 분포를 봅니다.
6. Save images를 누르면 원본 옆에 두 그림과 CSV를 저장합니다. 같은 이름이 있으면 덮어씁니다.

| 파일 | 내용 |
| --- | --- |
| `이름(1).tif`, `이름(1).csv` | 너비(최소 Feret 직경) |
| `이름(2).tif`, `이름(2).csv` | 길이(최대 Feret 직경) |

그림의 확장자는 원본을 따릅니다. 원본 위치를 모르면 저장할 폴더를 묻습니다. Build report
단계에서는 같은 측정값으로 PDF, HWPX, Word 보고서를 만들 수 있습니다.

확대는 800%까지 됩니다. 200%를 넘으면 픽셀이 흐려지지 않고 네모로 또렷하게 보입니다.
화면은 원본 해상도 그대로이며, 16비트 이미지만 표시용으로 8비트로 펴서 보여 줍니다.

## 측정 방법

- 길이: 최대 Feret 직경. 입자 윤곽에서 가장 먼 두 점 사이의 거리입니다.
- 너비: 최소 Feret 직경. 입자를 사이에 끼우는 평행선 두 개의 간격이 가장 좁을 때의 값입니다.
  길이선과 수직일 필요는 없습니다. 선의 양 끝은 입자 윤곽에 닿게 그립니다.
- Edit lines의 Width 토글(Minimum / Perpendicular)은 화면에 보이는 자동 너비선만 바꿉니다.
  Perpendicular는 길이선에 수직인 방향의 폭입니다. `이름(1)`은 토글과 관계없이 최소 Feret
  직경으로 저장되고, 손으로 그은 선은 그대로입니다.
- Correction factor: 표, Details, CSV, 저장 그림의 모든 길이에 곱하고 면적에는 제곱을 곱합니다.
  입자를 찾는 기준(최소 면적 등)에는 쓰지 않습니다. 마지막에 쓴 값이 다음 이미지의 기본값이
  되며, 이미 만든 분석에는 다시 분석해야 반영됩니다.
- 자동 검출은 이미지 가장자리에 잘린 입자, 다른 입자와 겹친 입자, 세워진 입자, 배경으로 보이는
  영역, 너무 작은 영역을 뺍니다. 빠진 입자는 Select particles에서 클릭해 넣을 수 있습니다.

## 폴더 일괄 처리

Load image 화면에서 Process a folder…를 누르고 폴더를 고릅니다. Correction factor를 확인한 뒤
Start를 누르면 폴더 안의 모든 이미지에서 입자를 찾아 `이름(1)`, `이름(2)` 그림과 CSV를 원본 옆에
저장합니다. 스케일은 각 파일에서 읽고, 스케일이 없는 이미지는 px로 잽니다. 둘 다 있는 이미지는
건너뛰고 하나라도 없으면 다시 분석해 덮어씁니다. 결과는 Open analysis에서 열어 고친 뒤 다시
저장하면 됩니다.

## 라벨링

1. 시작 화면에서 Labeling을 고르고 이미지를 엽니다.
2. 분석 영역, 최소 면적, 샘플링을 정하고 자동 분석을 시작합니다. 스케일 보정은 선택입니다.
3. 객체 안을 클릭하면 SAM 결과가 바로 반영됩니다. 기존 객체 안을 클릭하면 그 객체만 고치고
   다른 객체의 픽셀은 건드리지 않습니다.
4. Shift+클릭은 같은 객체에 포함 점을 더하고, 우클릭이나 Point −는 제외 점을 찍습니다.
   New object를 누르면 프롬프트가 초기화됩니다.
5. 반영 전에 결과를 보고 싶으면 Apply point edits immediately를 끄고 후보를 골라 Enter로
   반영합니다.
6. 점만으로 어려운 객체는 Box로 영역을 지정하고 Preview를 누릅니다. More tools에서 다각형,
   타원, 잘라내기를 쓸 수 있습니다.
7. Select로 객체를 골라 지우거나 합칩니다. Ctrl+Z는 프롬프트나 저장된 수정을 되돌립니다.
8. Save images로 인스턴스 마스크를 저장합니다. 기존 파일을 덮어쓰지 않도록 새 폴더를 만듭니다.

| 파일 | 내용 |
| --- | --- |
| `image.png` | 마스크와 좌표가 맞는 RGB 8비트 이미지 |
| `instances.png` | 16비트 인스턴스 맵. 배경은 0, 객체마다 고유 ID |
| `instances.npy` | 같은 인스턴스 맵의 NumPy 배열 |
| `instances_preview.png` | 눈으로 확인하는 색상 미리보기 |
| `instances.json` | ID, 면적, 박스, 프롬프트, 모델 출처 |
| `original.*` | 불러온 원본 파일 그대로 |

색상 미리보기는 학습용 라벨 맵이 아닙니다. `instances.png`를 회색 8비트로 변환하지 마세요.
ID는 삭제 이력 때문에 건너뛸 수 있고 최대 65535입니다. 분석 영역 밖은 0으로 저장됩니다.
16비트 원본은 `image.png`에서는 정규화되지만 `original.*`에는 그대로 남습니다.

## 업데이트

Load image 화면의 Check for updates로 GitHub의 최신 릴리스를 확인합니다. 버전이 바뀌어도
대개 `LabImage.exe`와 `_internal/ui`만 달라지므로 릴리스에는 작은 패치 zip(약 50 MB)이 들어
있습니다. 앱이 패치를 받아 종료한 뒤 파일을 바꾸고 다시 시작합니다. 라이브러리나 모델이
바뀐 릴리스는 전체 설치가 필요하다고 알려 줍니다.

## 소스에서 실행과 빌드

모델(`checkpoints/`)과 SAM 2 코드(`vendor/sam2`)는 저장소에 없고 배포 zip에만 들어 있습니다.
빌드는 `.venv/Scripts/python.exe -m PyInstaller packaging/LabImage.spec --workpath build/labimage --noconfirm`로
합니다. `LabImage.exe`는 `_internal` 폴더와 함께 배포합니다.

릴리스할 때는 `scripts/app_update.py`의 `VERSION`을 올리고(`_internal`이 바뀌었으면 `BASE`도 같은
값으로) 빌드한 뒤, 전체 zip과 패치 `LabImage-v<version>-patch-from-v<BASE>.zip`을 게시합니다.
