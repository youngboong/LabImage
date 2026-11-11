# CNT learned centerline: plan

Status: plan only, no code changed. Target reader: the coding agent. Builds on `docs/cnt-design.md` (Oriented tracker), `scripts/cnt_detect.py` VERSION 2, `scripts/cnt_eval.py`, `validation/cnt-eval/report.md` (2026-11-09).

Goal: learn a per-pixel "user would trace a tube centerline here" map `P` from the yellow labels and feed it into the existing click-guided tracker cost. The click interaction (two end clicks, Shift-click waypoints) is unchanged. Width is out of scope: `X(3).tif` is not read.

Why this should fix the reported failures: the band filter in `track_segment` responds to *any* bright elongated structure at the estimated width, so at a crossing both strands cost the same and the shorter one wins (strand jumps, U-shortcuts). A map trained on the user's own lines learns what the user calls a tube (ribbon centre, not an edge; the continuing strand, not the crossing one) and does not depend on the width estimate, which is what breaks thin fibres.

## 0. Hardware and stack (checked 2026-11-09)

- CPU: Intel Core Ultra 9 285K, 24 threads, 63 GB RAM. OpenVINO 2025.4 sees `CPU`, `GPU` (Intel iGPU), `NPU`.
- `torch 2.7.1+cpu`, `torchvision 0.22.1+cpu`. No XPU build, no CUDA. `onnx`, `segmentation_models_pytorch`, `albumentations`, `timm`, `nncf` are not installed and are not needed.
- `openvino.convert_model(torch_module, example_input=...)` converts a torch module directly, so no ONNX dependency. Training runs on CPU with torch; the app runs the model with OpenVINO only (no torch needed for this model at runtime).

## 1. Data after the user's rules

Rule: `CNT/261103` only images whose number (after `-`) is <= 30, unnumbered included by default; `CNT/261105` all. Labels are the yellow (`R>150, G>150, B<110, min(R,G)-B>60`) components of `X(2).tif` with bbox extent >= 60 px (smaller = text glyphs), as in `cnt_eval.gt_tubes`. "Simple" = skeleton with 2 tips, "complex" = more tips (crossing/branched polylines). Both are positives for training. Counts were measured with `cnt_eval.discover/gt_tubes` on the footer-cropped ROI.

| Set | Images | Simple polylines | Complex polylines | Yellow px (>=60 px components) |
|---|---|---|---|---|
| Eligible, all | **45** | **91** | **30** | ~56.8k |
| of which >= 1kx | 21 | 24 | 18 | |
| of which < 1kx | 24 | 67 | 12 | |
| Excluded (261103, number > 30) | 8 | 43 | 13 | |

- Excluded: `CNT_powder_200x-31`, `300x-32`, `300x-34`, `300x-35`, `500x-33`, `500x-37`, `500x-38`, `600x-36`. Never read for training or evaluation.
- Unnumbered, included by default, **user to confirm**: `CNT/261103/CNT_powder_1kx.tif` (1 simple polyline), `CNT/261103/CNT_powder_500x.tif` (1 simple + 1 complex).
- Orphans, no base image, skipped automatically: `CNT_powder_1kx-5.(2).TIF`, `CNT_powder_500(2).tif`. `CNT_powder_1kx_.tif` has no label file: unlabelled, unused.
- Eligible by magnification: 100x 2, 120x 1, 150x 1, 200x 7, 300x 2, 500x 9, 700x 1, 800x 1, 1kx 17, 2kx 2, 2.5kx 1, 3kx 1.
- All 91 simple polylines pass the current "certain" rule (>= 60 px, 5 px from the ROI edge).
- The polylines are ~3 px thick, so the usable centerline length is about 19k px in total. This is a small dataset: the model must be small and augmentation heavy.
- `CNT_powder_100x-30` alone has 19 simple polylines; at 100x (2.7 um/px) a labelled "tube" is a bundle 2–5 px wide. See risks.

## 2. Dataset build (`scripts/cnt_train.py`, function `build_samples`)

One script, dev only, not bundled. Reuses `cnt_eval.discover`, `cnt_eval.yellow`, `lab_footer.detect_information_footer`.

1. **Discovery.** `discover(['CNT/261103','CNT/261105'], 0, set())`, then drop 261103 images with number > 30 (`re.search(r'-(\d+)$', stem)`). Also discover app-accepted traces (section 6).
2. **Crop.** `gray = L(base)[:detect_information_footer(L(base))]`; the `(2)` image is cropped to the same rows (768 for most, 818 for the old layout).
3. **Centerline raster.** `yellow(two, bottom)` -> components with extent >= 60 -> `skeletonize` each (simple and complex alike). Union of skeletons = `C` (1-px centerlines; the small skeleton spurs at crossings are harmless under the soft target).
4. **Soft target.** `d = distance_transform_edt(~C)`; `t = exp(-d^2 / (2*sigma^2))` with `sigma = 2.5 px`. This absorbs the user's hand offset (the lines are drawn free-hand, a few px off the true centre) and the 3 px pen width.
5. **Loss weight `w` (partial labels).** The user labels only some tubes, so unlabelled tubes must not be taught as background.
   - `w = 1` where `d <= 3*sigma` (positives and their immediate flanks).
   - `w = 0` (ignore) where `d > 3*sigma` and the image is "tube-like": `sato` ridge response `R` (`cnt_detect.ridge_response`) above its robust threshold `median + 3*MAD`, dilated by 5 px. This covers unlabelled tubes, bundles and bright edges.
   - `w = 1`, target 0, everywhere else (confident background: flat, dark, or low ridge response far from any label).
   - Expected: ignore covers 20–40 % of the ROI on busy images; that is fine.
6. **Normalisation.** Per image: `(gray - p1) / (p99 - p1)` clipped to `[0, 1]`, so SEM brightness/contrast drift is removed before augmentation.
7. **Scale.** No resampling to a common um/px. Reason: a common scale would upsample 100x images 10x (nonsense) or shrink 3kx images to a few px of tube. Instead: train at native pixels with random scale augmentation 0.7–1.4 and a receptive field (~100 px) that covers all tube widths seen (3–30 px). Per-magnification metrics (section 5) decide whether low-mag images help or hurt; if they hurt, drop `< 300x` from training (one list edit).
8. **Patches.** Random 256x256 crops; 70 % of crops centred within 40 px of a positive pixel, 30 % uniform. ~40 crops per image per epoch, drawn fresh each epoch.
9. **Augmentation** (numpy/cv2, applied to gray, `t` and `w` together where geometric): random flips and rot90; free rotation 0–360 deg (bilinear, crop the valid centre); scale 0.7–1.4; gamma 0.7–1.4; contrast 0.8–1.25; additive Gaussian noise sigma 0.01–0.05; Gaussian blur sigma 0–1.0 (p=0.3). SEM-specific: horizontal line-noise (per-row offset, sigma 0.02, p=0.3) and a low-frequency multiplicative gradient (charging, +-15 %, p=0.3). No elastic deformation (it bends thin tubes into unrealistic shapes).
10. **Split: 5-fold grouped cross-validation at image level**, folds written once to `validation/cnt-learning/folds.json` (seeded; stratified by folder and by magnification bin `<300x`, `300–800x`, `>=1kx` so every fold has ~4 `>=1kx` images). Reason: only 24 simple `>=1kx` polylines exist; a single 20 % test set would hold ~5 of them and the primary metric would be noise. Out-of-fold predictions give a held-out result for all 45 images. The deployed model is then trained on all 45. Baseline needs no training, so it is scored on the same images.
    - Within each training fold, 1 image per magnification bin is the early-stopping validation image (so 3 of ~36).

Output of `build_samples`: an in-memory list of `(gray_f32, target_f32, weight_f32, meta)`; no intermediate files (45 images x 3 arrays x ~0.8 MP floats = ~400 MB, fits in RAM). Optionally cache to one `.npz` in `validation/cnt-learning/` for reruns.

## 3. Model and training

- **Architecture:** plain U-Net, 1 input channel, 4 resolution levels, channels 16-32-64-128 (bottleneck 128), two 3x3 conv + BatchNorm + ReLU per level, bilinear upsampling with skip concat, 1x1 head, sigmoid. About 0.5 M parameters; receptive field ~110 px. Input H, W must be multiples of 16 (pad with reflect at inference).
- **Loss:** `BCEWithLogits(logit, t)` with per-pixel weight `w`, positives upweighted by `pos_weight = (sum w*(1-t)) / (sum w*t)` computed once on the training fold (~20–50), plus soft Dice on `w > 0` pixels (`2*sum(w p t) / sum(w (p+t))`). Sum of both. Soft Dice keeps thin lines from collapsing; weighted BCE keeps calibration for the cost blend.
- **No orientation head.** The tracker already carries heading on its lattice; an isotropic centerline map is all the cost needs. Revisit only if crossings still fail with `P` in the cost.
- **Optimiser:** AdamW lr 1e-3, weight decay 1e-4, cosine decay, batch 16, 40 epochs of ~1400 patches (= ~3500 steps), `torch.set_num_threads(16)`. Early stopping on validation weighted BCE, patience 8 epochs.
- **Budget on this CPU:** a 0.5 M-param U-Net at 256x256, batch 16, forward+backward ~0.5–0.8 s per step -> ~35–45 min per fold, ~3.5 h for the 5 folds + final model. Run overnight, or run folds in parallel with 4 threads each (24 threads, 63 GB) for ~1.5 h total.
- **Export:** `ov.convert_model(model.eval(), example_input=torch.zeros(1,1,768,1024))` with dynamic H, W, `ov.save_model(..., 'checkpoints/openvino/cnt_centerline.xml', compress_to_fp16=True)`. Weight file ~1 MB. Also save the torch `state_dict` under `validation/cnt-learning/` for retraining.
- **Alternatives considered:**
  - Learned pixel classifier on hand features (sato multi-scale, oriented filter bank, local statistics) with a random forest / gradient boosting: no torch, trains in minutes, but cannot learn "which strand continues" (needs context the features do not have). Keep as the fallback if the U-Net overfits visibly (training loss falls, out-of-fold distance does not improve).
  - Adding `sato R` as a second input channel: helps with very little data, but ties the model to the hand-set sigma range. Try only if the 1-channel model is clearly worse than baseline at 500x–1kx.
  - Fine-tuning a pretrained encoder (SAM2 Hiera is bundled): far too heavy for < 1 s full-image inference on CPU and for 45 images.
  - Direct path regression / learned Dijkstra costs end-to-end: more code, no evidence it is needed.

## 4. Integration into the tracker

Files: `scripts/cnt_detect.py`, `scripts/lab_editor.py`. No API or UI change.

1. **Loader** (`cnt_detect.centerline_map(gray) -> np.float32 (H, W) | None`, cached compiled model at module level):
   - Path `app_paths.ASSET_ROOT / 'checkpoints/openvino/cnt_centerline.xml'`. Missing file, missing `openvino`, or any exception -> log once, return `None`.
   - Normalise as in training (p1/p99), reflect-pad to multiples of 16, `core.compile_model(path, 'CPU')`, run, crop back. Return `P` in `[0, 1]`.
   - Device: CPU in-process first. The whole 1024x768 pass of a 0.5 M-param U-Net is ~0.2–0.5 s on this CPU, within the 1 s budget, and it runs once per image. Use the existing `lab_gpu_worker.GPUWorker` only if measured CPU time exceeds 1 s on the target laptops (it adds a process and the GPU fallback logic).
2. **Cache:** `LabEditor.tube_ridge` computes `state['tube_cache']['P'] = centerline_map(state['gray'])` next to `ridge_response`. Same lifetime as the ridge: once per dataset, survives revisions and undo.
3. **Cost blend in `track_segment(f, a, b, width, heading=None, P=None)`:** crop `P` with the same box as `crop`, downsample to the lattice with `cv2.resize(..., INTER_AREA)`, then after the per-width max:
   ```
   if P is not None: response = (1-TRACK_LEARNED)*response + TRACK_LEARNED*TRACE_CLIP*p_small
   ```
   `TRACK_LEARNED = 0.6` (new constant; tune on out-of-fold images, grid 0.4/0.6/0.8/1.0). `P = 1` then reaches the clip level, so a confident centerline costs the floor `1/(eps+4)`; a strand with `P ~ 0` keeps 40 % of the band response, so the trace still follows the ridge where the model is unsure (thin fibres, 3kx). The sub-cell parabola and the bend cost are untouched.
   - Alternative to test in the same grid: multiplicative gating `response *= 0.3 + 0.7*p_small`, which targets strand jumps more directly but can starve the path where `P` is wrong. Pick whichever wins on out-of-fold `>=1kx` with 0 waypoints.
4. `trace_tube` passes `ridge.get('P')` into every `track_segment` call; `measure_spot` passes it too (one argument). `trace_width`, `end_heading`, `finish_candidate`, width code: unchanged.
5. **Latency:** ridge 0.7–1.0 s (existing) + `P` 0.2–0.5 s, both once per image on the first trace. Per trace: one extra `cv2.resize` on a crop, negligible; traces stay ~0.1 s.
6. **Bundling:** `packaging/LabImage.spec` already copies the whole `checkpoints/openvino` folder (`datas += [(root/'checkpoints/openvino', 'checkpoints/openvino')]`), so placing `cnt_centerline.xml/.bin` there bundles it with no spec change. `lab_openvino.available()` is SAM-specific and is not touched.
7. **Fallback:** `P is None` -> exactly VERSION 2 behaviour. Bump `cnt_detect.VERSION` to 3 and record `tube.learned = P is not None` in `tube_annotation` so evaluations and user reports can tell which cost produced a trace.
8. **Tests** (`tests/test_cnt_detect.py`): `track_segment(..., P=None)` equals the current result on the synthetic tubes; `P = ones` and `P = zeros` run and return a path between the clicks; `centerline_map` returns `None` when the model file is absent (monkeypatched path).

## 5. Evaluation (`scripts/cnt_eval.py` extensions)

- Default `--min-mag 0`. New rule in `discover`: drop 261103 numbers > 30 (hard-coded list or `--max-number 30 --max-number-folder 261103`), listed under "Excluded by rule".
- New `--model {auto,none}`: `none` forces `P = None` (baseline); `auto` loads `checkpoints/openvino/cnt_centerline.xml`. New `--folds validation/cnt-learning/folds.json --fold-models DIR` so each image is scored with the model that did not see it (out-of-fold). Without `--folds` it scores the deployed model (optimistic on training images; the report says so).
- `--waypoints` accepts a list `0 1 2`; one run writes all three.
- **Primary metric, new:** mean symmetric distance per tube: resample trace and GT to 1 px, `0.5*(mean_dist(trace->GT) + mean_dist(GT->trace))`. Report median and p90 over tubes. Keep length relative error (median |e|, p90) and match rate (`matches`, 70/70 at `tol`).
- Breakdown tables: per magnification bin (`<300x`, `300–800x`, `>=1kx`) x waypoints x model. Per-tube rows in `per_tube.csv` gain `sym_dist`, `model`, `waypoints`, `fold`.
- Overlays: baseline trace in magenta, learned trace in cyan, GT yellow, in one PNG per image; plus a `P` heatmap PNG per image for inspection.
- Width metrics stay in the script but are not part of this comparison.
- **Acceptance (out-of-fold, `>=1kx`, 24 tubes; baseline numbers from the current report in brackets):**

| Metric | 0 waypoints | 2 waypoints |
|---|---|---|
| median symmetric distance | <= 7 px [14] | <= 4 px [5.5] |
| p90 symmetric distance | <= 20 px [46] | <= 9 px [13] |
| length median \|err\| | <= 5 % | <= 3 % [4 %] |
| match rate | >= 0.85 | >= 0.95 [0.92] |

  For `< 1kx` bins: report only, no gate, but the learned model must not be worse than baseline by more than 10 % on median distance in any bin (otherwise drop that bin from training and retrain; see section 2.7).

## 6. Active-learning loop

- **Labels already exist.** Every accepted trace is saved by `LabEditor.trace_tube` as an annotation with `source: 'cnt_trace'`, `review_status: 'user_accepted'`, `manual_measurements.length` = the decimated path (x, y in ROI px), in the dataset's `edit.json` under `outputs/<...>/`, next to the saved gray image (`pore_editor.save_images`). User edits to a path and deletions are reflected there. No new format, no new storage.
- `build_samples` gets a second source: `--accepted outputs` scans `**/edit.json`, takes annotations with `tube.kind in ('t','td')` and a `manual_measurements.length` path, rasterises the polyline (`cv2.polylines`, 1 px) as the centerline `C` of that image, with the same soft target and ignore rules. Weight 0.5 for traces produced with the learned cost (`tube.learned == True`) and not edited, to limit self-confirmation; weight 1 for traces the user moved (compare the path to a fresh `trace_tube` result on the fly: moved if mean distance > 2 px) or produced without the model.
- Shared gray images between the `CNT/` folders and `outputs/` (same file traced in the app) are deduplicated by the SHA-1 of the gray array; their label sets are unioned.
- **Retrain:** `scripts/cnt_train.py --accepted outputs --out checkpoints/openvino/cnt_centerline.xml` (single final model, all data, same recipe, ~45 min), then `scripts/cnt_eval.py --waypoints 0 1 2` on the fixed `CNT/` folds as the regression check before copying the weights into a build. A one-line entry in `validation/cnt-learning/history.md` (date, image count, out-of-fold numbers) tracks drift.
- Cross-validation is rerun only when the label set grows by more than ~30 %.

## 7. Risks and open questions for the user

1. **Unnumbered images** `CNT_powder_1kx.tif` and `CNT_powder_500x.tif` (261103): included by default. Confirm they were labelled correctly.
2. **Low magnification (100–300x):** labels there follow bundles 2–5 px wide, not single tubes, and `100x-30` alone holds 19 of the 91 simple polylines. This may teach "bundle centre" and bias thin-fibre behaviour at 1kx. The per-bin evaluation decides; are low-mag traces actually used in the lab, or can `< 300x` be dropped from both training and the targets?
3. **Hand-drawn offset.** The user's polylines are a few px off the true centre and the model will learn that offset as noise (sigma 2.5 px). The symmetric-distance metric measures agreement with the user's line, not with the physical centre; 2–3 px is the floor.
4. **Small data.** ~19k centerline px from 45 images. Expect the model to be a strong learned ridge filter, not a semantic detector; crossings with both strands labelled in different images may still be ambiguous. Accepted traces from the app (section 6) are the way to grow the set; roughly 100+ further tubes should be collected before expecting another step.
5. **Self-training bias.** Accepting an uncorrected learned trace as a label confirms the model's mistakes; the 0.5 weight limits but does not remove this.
6. **Runtime cost.** +0.2–0.5 s on the first trace per image (CPU). If the target laptops are slower, the GPU worker path exists but adds complexity; confirm the hardware the app ships to.
7. **Torch stays dev-only.** The app needs only the OpenVINO `.xml/.bin` (~1 MB); nothing new is added to the installer except these two files.

## Design (verified)

Verified 2026-11-09 with throwaway prototypes in the session scratchpad (`learn/labels4.py`, `learn/unet.py`, `learn/timing2.py`, `learn/ovtime.py`). Where this section disagrees with sections 1–7 above, this section wins. User decisions folded in: width is out of scope. Positives come **only** from the yellow lines in `X(2).tif`: no `(3)` width marks, no app-accepted traces, no pseudo-labels. Section 6 (active learning) is **deferred**, not built.

### D1. Dataset rules (final)

- `CNT/261105`: every image with a `(2)` label file.
- `CNT/261103`: only images whose stem ends in `-<n>` with `n <= 29`. Excluded: `100x-30` (bundle polylines), every number >= 30 (`200x-31`, `300x-32/34/35`, `500x-33/37/38`, `600x-36`), every unnumbered image (`CNT_powder_1kx`, `CNT_powder_500x`, `CNT_powder_1kx_`, and the orphan `CNT_powder_500(2)`). `discover` already skips the orphan `CNT_powder_1kx-5.(2).TIF` because it has no base image.
- Rule as code, shared by train and eval: `eligible(folder, stem) = folder.endswith('261105') or (m := re.search(r'-(\d+)$', stem)) and int(m[1]) <= 29`.
- Measured counts (footer-cropped ROI, `gt_tubes`): **42 images, 70 simple + 28 complex polylines**.

| bin | images | simple polylines |
|---|---|---|
| `<300x` | 10 | 30 |
| `300–800x` | 12 | 17 |
| `>=1kx` | 20 | 23 |

  By magnification: 100x 1, 120x 1, 150x 1, 200x 7, 300x 2, 500x 8, 700x 1, 800x 1, 1kx 16, 2kx 2, 2.5kx 1, 3kx 1. The excluded set has 11 images, 64 simple + 15 complex polylines.

### D2. Label extraction (verified on overlays)

Per image: `gray = L(base)[:bottom]`, `bottom = detect_information_footer(L(base))`, `y = cnt_eval.yellow(two, bottom)`.

1. **Components:** 8-connected components of `y`. Keep those with bbox extent >= 60 px (`keep`). Smaller ones are text glyphs.
2. **Centerline `C`:** `prune(skeletonize(keep), spur=40)`, then `skeletonize` again. `prune` deletes every tip-to-junction branch of <= 40 px, for up to 3 rounds. Reason: the label text (`T7=320.04 µm`) is drawn in the same yellow and often **touches the line**, so it merges into the >= 60 px component. Before pruning, 28 components had more than 2 tips. Checked on the overlays: in `100x-12` T7 (6 tips), `2000x-8` T3 (5) and `1kx-12` T3 (7), the cause was text merged into the line. The other 25 components were not inspected one by one. After pruning these are clean 2-tip lines. True crossings, whose branches are longer than 40 px, survive (e.g. `1kx-5` keeps 4 tips). Known cost: when a line end passes *through* its own text, it loses up to 40 px (seen on `100x-12` T7, ~30 px). That stretch falls inside the text box, which is ignored (below), so it is not taught as background.
   - Rejected alternative: cutting text boxes out of `y` before the size filter. It split short lines below 60 px and deleted 2 of the 7 tubes on `100x-12`.
3. **Target:** `d = distance_transform_edt(~C)`, `t = exp(-d²/(2·2.5²))`.
4. **Weight `w` (ignore rule, revised):** `w = 0` where `d > 7.5` (3σ) and any of these holds:
   - `tube`: multi-scale sato at **fixed pixel scales** `(1.5, 3, 6, 10)` on `f = g/255 − gaussian(g/255, 40)` (bright ridges), with `R > median(R) + 3·1.4826·MAD(R)`;
   - `bright`: `gaussian(gray, 3) > threshold_otsu(gaussian(gray, 3))`;
   - `text`: text boxes. A text box is the bbox of glyph components (< 60 px) after dilation with a 5×15 rectangle, padded by 3 px and extended left by 1.5× the box height. The left extension covers the `T<n>=` prefix, which touched the line and so is not a glyph component.
   - `tube | bright` is dilated by 5 px before the union.

   Everywhere else `w = 1`: the labelled line ± 7.5 px, and confident background.
   - Why this differs from the planner's `ridge_response` rule: `ridge_response` uses magnification-dependent sigmas (1.5–1.7 px at 100x). At low magnification it covers only fine fibrils. The 20–40 px bundles, which are what the user labels there, were left as **confident background**. Fixed pixel scales plus the Otsu bright mask cover bundles at every magnification, and the dark substrate stays background.
   - Measured ignore fraction: `1kx-12` 32 %, `1kx-5` 40 %, `500x-1` 48 %, `2000x-8` 49 %, `200x-3` 56 %, `100x-12` 60 %. The overlays show unlabelled tubes, bundles and debris covered, and the dark substrate between them kept as background. Cost: ~0.7 s per image.
5. **Normalisation:** `x = clip((gray − p1) / (p99 − p1), 0, 1)` over the whole ROI. This is `cnt_detect.normalise_gray`, shared by training and inference. The editor's `state['gray']` is the same footer-cropped ROI (`pore_editor.state`), so the statistics match.

Overlays (left: image; right: yellow = `C`, red = `d <= 7.5` band, blue = ignore, magenta = glyph pixels not in `C`): scratchpad `learn/CNT_powder_1kx-12_final.png`, `learn/CNT_powder_500x-1_final.png`, `learn/CNT_powder_100x-12_final.png`, plus `2000x-8`, `1kx-5` and `200x-3`. `learn/*_lab.png` show the old rule for comparison.

### D3. Model and training (measured)

- **U-Net** exactly as in section 3: channels 16-32-64-128, 2× (conv3×3, BN, ReLU) per block, max-pool down, bilinear up + concat, 1×1 head. **487,713 params.** The model outputs logits; the sigmoid is added inside the exported graph.
- **Measured CPU training speed** (batch 16, 256×256, forward + backward + AdamW step, Core Ultra 9 285K):

| setup | s/step | patches/s (total) |
|---|---|---|
| 1 proc, 24 threads | 0.68 | 23.5 |
| 1 proc, 24 threads, `channels_last` | 0.58 | 27.6 |
| 1 proc, 8 threads, `channels_last` | 0.67 | 23.8 |
| **3 procs × 8 threads, `channels_last`** | 1.33 each | **36** |
| 2 procs × 12 threads, `channels_last` | 0.92 each | 34.6 |
| 4 procs × 6 threads | 2.4 each | 26 |
| 6 procs × 4 threads | 3.5 each | 27 |

  bf16 autocast is not usable: `DNNL does not support bf16/f16 backward on the platform with avx2_vnni_2`. The planner's 56k patches per model would take ~4 h, so the budget is cut.
- **Config:** `channels_last`, `torch.set_num_threads(8)`, **3 processes in parallel**, in 2 waves: `[fold0, fold1, fold2]`, then `[fold3, fold4, final]`. Per model: **24 epochs × 1024 patches** (1536 steps, 24.6k patches), ~34 min at 12 patches/s. Total ≈ 70 min training + ~1 min label build + ~5 min OOF inference and eval grid ≈ **80 min**.
- AdamW lr 2e-3 (for the shorter schedule), weight decay 1e-4, cosine decay to 0, no warmup. **No early stopping:** fixed schedule, keep the last weights. The final model has no validation image, and folds must use the same recipe. Each fold logs weighted BCE on its 3 held-in validation images every epoch, for diagnosis only.
- Loss: weighted BCE (`pos_weight` from the training fold) + soft Dice on `w > 0`, as in section 3.
- Patches: 70 % centred within 40 px of a `C` pixel, 30 % uniform. Each is sampled from a 362×362 window, augmented, then centre-cropped to 256. Augmentation as in section 2.9.
- **Folds:** 5, image-level, seeded, stratified by bin: every fold holds 4 `>=1kx`, 2 `<300x` and 2–3 `300–800x` images. Written once to `validation/cnt-learning/folds.json`.
- **OpenVINO inference (measured, random-init model, fp16-compressed IR):**
  - convert + save: 1.1 s
  - `compile_model('CPU')`: 0.04 s
  - **1024×946 (padded to 1024×960): 0.10 s first call, 0.079 s warm**
  - 1024×768: 0.063 s
  - OV vs torch max abs difference: < 1e-4
  - `.bin` size: 949 KB

  This is well under the 0.5 s gate, so no GPU worker is needed.
- Export: `ov.convert_model(nn.Sequential(model, nn.Sigmoid()).eval(), example_input=torch.zeros(1,1,768,1024), input=[(1,1,-1,-1)])`, then `ov.save_model(..., compress_to_fp16=True)`.

### D4. Tracker integration (exact)

How `track_segment` works today:
- It computes a per-orientation response `o` (8, h, w). Each width scale is normalised by its 97th percentile, and `response` is the max over scales.
- `cost = 1/(TRACE_EPS + clip(response, 0, TRACE_CLIP)^TRACK_GAMMA)`, with `EPS = 0.05`, `CLIP = 2`, `GAMMA = 2`.
- Edge weight = step length × s × mean cost of the two cells, + `TRACK_TURN·width` per 22.5° bend.
- The sub-cell parabola reads `response`.

New code, right after the width loop (before `cost`):

```python
if P is not None:
    p = P[y0:y0+h*s, x0:x0+w*s]
    p = cv2.resize(p, (w, h), interpolation=cv2.INTER_AREA) if s > 1 else p
    response = (1-TRACK_LEARNED)*response + TRACK_LEARNED*TRACE_CLIP*p[None]
```

`response` is replaced, not copied, so the sub-cell parabola also centres on the blend. This pulls the path to the learned centre. The bend term is untouched.

Cost math at `TRACK_LEARNED = 0.6`:
- Tube with `r = 1, P = 1`: blend 1.6, cost 0.38 (baseline 0.95).
- Competing strand at a crossing with `r = 1, P = 0`: blend 0.4, cost 4.8. The learned strand is ~12× cheaper per px.
- Empty background `r = 0, P = 0`: cost 20 (unchanged).

`P` is isotropic, so heading still comes from `r` and the bend cost. Side effect: the per-px cost on a learned path drops ~2.5×, so the bend penalty becomes relatively ~2.5× stronger. That is why `TRACK_TURN` is in the grid.

**Grid (out-of-fold `P` only, 0 waypoints, all 42 images):**
- `TRACK_LEARNED ∈ {0.4, 0.6, 0.8, 1.0}` at `TRACK_TURN = 0.5`;
- the best of those with `TRACK_TURN = 0.25`;
- baseline (`--model none`) as reference.

That is 5 configs + baseline, run as parallel `cnt_eval` processes (~80 s each).

**Pick:** the lowest median symmetric distance on `>=1kx`. On a tie (< 0.3 px), pick the lower p90. Reject any config more than 10 % worse than baseline in median distance on any bin. Then set the constants in `cnt_detect.py`.

The multiplicative gate from section 4.3 is dropped. `λ = 1.0` already covers the "trust P only" extreme, and one blend form means less code.

### D5. File layout and signatures

**`scripts/cnt_detect.py`** (VERSION 3)

- Constants: `MODEL_FILE = 'checkpoints/openvino/cnt_centerline.xml'`, `TRACK_LEARNED = 0.6` (the grid result replaces it).
- `normalise_gray(gray: np.ndarray) -> np.ndarray`: float32 in [0, 1], p1/p99.
- `centerline_map(gray: np.ndarray, model_path: str | Path | None = None) -> np.ndarray | None`:
  - Returns float32 (H, W) in [0, 1].
  - Default path: `app_paths.ASSET_ROOT / MODEL_FILE`.
  - The compiled model is cached in a module dict keyed by path.
  - Reflect-pads to a multiple of 16, runs, crops back.
  - Missing file, no `openvino`, or any exception: log once, return `None`.
- `track_segment(f, a, b, width, heading=None, P=None)`: blend as in D4.
- `trace_tube(gray, ridge, points)`: passes `ridge.get('P')` to every `track_segment` call and sets `c['learned'] = ridge.get('P') is not None`.
- `measure_spot` and the width code: unchanged, because width is out of scope.

**`scripts/lab_editor.py`**

- `tube_ridge`: inside the existing `if 'tube_cache' not in state:` block, after `ridge_response(...)`, add `state['tube_cache']['P'] = centerline_map(state['gray'])`. Same lifetime as the ridge.
- `tube_annotation`: add `learned=bool(c.get('learned'))` to the `tube` dict.

**`scripts/cnt_train.py`** (dev only, not bundled, imports torch)

- `eligible(folder: str, stem: str) -> bool`
- `prune(skeleton: np.ndarray, spur: int = 40, rounds: int = 3) -> np.ndarray`
- `label_maps(gray: np.ndarray, two_path: Path, bottom: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]`: returns `(C, t, w)` as in D2.
- `build_samples(folders=('CNT/261103', 'CNT/261105')) -> list[dict]`: keys `name, mag, bin, x (normalised), t, w`. Cached to `validation/cnt-learning/samples.npz`.
- `make_folds(samples, k=5, seed=0) -> dict[str, int]`: writes `validation/cnt-learning/folds.json`.
- `class UNet(nn.Module)`, `train(samples, names, epochs=24, patches=1024, threads=8, seed=0) -> UNet`, `export(model, xml_path)`.
- CLI:
  - `--fold {0..4|final}`: trains one model. Folds go to `validation/cnt-learning/fold{k}.xml`; final goes to `checkpoints/openvino/cnt_centerline.xml`. A `.pt` state_dict is saved next to each.
  - `--all`: runs the 2 waves of 3 subprocesses.
  - `--oof`: for each image, runs `centerline_map(gray, fold{k}.xml)` with the fold model that did not see it, and saves `validation/cnt-learning/oof/<stem>.npy` (float16).
  - `--overlays`: writes the D2 overlays to `validation/cnt-learning/labels/`.

**`scripts/cnt_eval.py`**

- `--min-mag` defaults to 0. `discover` drops images where `eligible(...)` is false and lists them under Skipped as "excluded by rule".
- `--model {auto,none,oof}` (default `auto`):
  - `none`: `ridge['P'] = None`.
  - `auto`: `centerline_map(gray)`.
  - `oof`: loads `oof/<stem>.npy` (needs `--folds`).
- `--folds validation/cnt-learning/folds.json`: adds the fold id per image to `per_tube.csv`.
- `--waypoints 0 1 2` takes a list.
- `--learned-weight` and `--turn` override `cnt_detect.TRACK_LEARNED` and `TRACK_TURN` for the grid.
- `sym_dist(a, b) = 0.5*(mean NN dist a→b + mean NN dist b→a)` on 1-px resampled paths.
- Report: median and p90 symmetric distance per bin (`<300x`, `300–800x`, `>=1kx`) × waypoints, plus length median |err| and match rate. `per_tube.csv` gains `sym_dist, model, waypoints, fold, bin`.
- Overlays: GT in yellow; the trace in magenta (`--model none`) or cyan (with a model). With a model, also one `P` heatmap PNG per image.

**Weights:** `checkpoints/openvino/cnt_centerline.xml/.bin` (~1 MB). The spec's `checkpoints/openvino` copy already bundles them.

### D6. Tests (`tests/test_cnt_detect.py`, `tests/test_cnt_train.py`)

1. The existing tracker tests pass unchanged (the `P=None` path is byte-identical).
2. `trace_tube` with `ridge['P'] = ones` and with `ridge['P'] = zeros` returns a path that starts and ends at the clicks.
3. Crossing test: render `SCURVE` and `CROSS`, and set `P` to a Gaussian band (σ 2.5) on `SCURVE` only. A trace between the `SCURVE` ends has mean distance < 3 px to `SCURVE`.
4. `centerline_map` returns `None` for a missing model path. When the real model file exists, the output shape equals the input shape for a 946×1023 array and values are in [0, 1] (skip otherwise).
5. `cnt_train.eligible`: `('CNT/261103', 'CNT_powder_1kx-29')` is True. `-30`, `-31` and unnumbered `CNT_powder_1kx` are False. Any `261105` stem is True.
6. `label_maps` on a synthetic `(2)` image: a 300 px yellow polyline plus `cv2.putText('T1=12.3 um')` overlapping it. Expected: `C` has 1 component with 2 tips, every `C` pixel is within 2 px of the drawn line, and the text region has `w == 0`.

### D7. Implementation order (each step has a check)

1. `cnt_detect`: `normalise_gray`, `centerline_map`, `P` in `track_segment`/`trace_tube`, VERSION 3. `lab_editor`: the `tube_ridge` hook and the `learned` flag. **Check:** tests 1–4 pass and the existing suite passes.
2. `cnt_eval`: rule, flags, `sym_dist`, bins. **Check:** `--model none --waypoints 0 2` runs on the 42 images. Record these baseline numbers as the new reference (the old report used 21 images, including the now-excluded `CNT_powder_1kx`).
3. `cnt_train` labels: `build_samples`, `--overlays`. **Check:** tests 5–6 pass and there are 42 samples. Overlays for `1kx-12`, `500x-1` and `100x-12` match D2 (ignore 32 / 48 / 60 % ± 2).
4. Training smoke: `--fold 0 --epochs 1 --patches 256`. **Check:** finishes in < 1 min and the loss decreases. The exported xml loads in `centerline_map` and runs in < 0.2 s on a 1024×946 image.
5. `--all`. **Check:** 6 models after ~70 min. Every fold's train loss falls, and its logged val wBCE ends below its epoch-1 value. On a `P` heatmap of one held-out `>=1kx` image, labelled tubes are bright and the substrate is dark.
6. `--oof`, then the D4 grid. **Check:** the chosen constants are written into `cnt_detect.py`, and the grid table is in `validation/cnt-learning/report.md`.
7. Acceptance: `cnt_eval --model oof --folds ... --waypoints 0 1 2`. **Check:** the D8 gates. Then trace one tube in the app: the first trace adds < 0.2 s, and `tube.learned == true` in `edit.json`.

### D8. Acceptance (out-of-fold, `>=1kx`, 23 tubes)

The planner's targets are kept: nothing measured here argues for changing them. The bracketed baselines come from the old 21-image report and are refreshed in step 2.

| Metric | 0 waypoints | 2 waypoints |
|---|---|---|
| median symmetric distance | <= 7 px [14] | <= 4 px [5.5] |
| p90 symmetric distance | <= 20 px [46] | <= 9 px [13] |
| length median \|err\| | <= 5 % | <= 3 % [4 %] |
| match rate | >= 0.85 | >= 0.95 [0.92] |

`<1kx` bins: report only. The learned model must not be more than 10 % worse than baseline in median distance in any bin. If it is, drop `<300x` from training and rerun one wave. Fallback if the gates fail: ship with `P` disabled (file absent → VERSION 2 behaviour); no code revert is needed.
