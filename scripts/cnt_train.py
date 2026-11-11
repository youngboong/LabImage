"""Dev-only (not bundled): train the learned CNT centerline map from the yellow lines of X(2).tif. Imports torch.

    .venv/Scripts/python.exe scripts/cnt_train.py --overlays        # label overlays -> validation/cnt-learn/labels/
    .venv/Scripts/python.exe scripts/cnt_train.py --fold 0          # one model (0..4 or final)
    .venv/Scripts/python.exe scripts/cnt_train.py --all             # 2 waves of 3 subprocesses x 8 threads: fold0-2, then fold3, fold4, final
    .venv/Scripts/python.exe scripts/cnt_train.py --oof             # out-of-fold maps -> validation/cnt-learn/oof/<stem>.npy

Positives come only from the yellow polylines of X(2).tif (no (3), no app traces, no pseudo-labels). See docs/cnt-learning-plan.md, D1-D5.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from skimage.filters import sato, threshold_otsu
from skimage.morphology import skeletonize

import cnt_detect
from cnt_eval import BINS, discover, eligible, luminance, mag_bin, yellow  # noqa: F401  (eligible is re-exported: one rule for train and eval)
from lab_footer import detect_information_footer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'validation/cnt-learn'
FINAL_XML = ROOT/cnt_detect.MODEL_FILE
SIGMA = 2.5                      # soft-target width, px: hand offset + 3 px pen
SPUR = 40                        # label-text spurs up to this long are pruned from the skeleton
MIN_EXTENT = 60                  # yellow components smaller than this are text glyphs
PATCH = 256
N8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


# ---------------------------------------------------------------- labels (D2)

def prune(skeleton, spur=SPUR, rounds=3):
    """Delete every tip-to-junction branch of <= `spur` px (label text touching the line), then re-skeletonize."""
    sk = skeleton.copy()
    for _ in range(rounds):
        neighbours = ndi.convolve(sk.astype(np.uint8), np.ones((3, 3), np.uint8), mode='constant')-sk
        changed = False
        for y0, x0 in np.argwhere(sk & (neighbours == 1)):
            path, prev, cur = [], None, (int(y0), int(x0))
            while len(path) <= spur:
                path.append(cur)
                nxt = [(cur[0]+dy, cur[1]+dx) for dy, dx in N8 if 0 <= cur[0]+dy < sk.shape[0] and 0 <= cur[1]+dx < sk.shape[1]
                       and sk[cur[0]+dy, cur[1]+dx] and (cur[0]+dy, cur[1]+dx) != prev and (cur[0]+dy, cur[1]+dx) not in path]
                if len(nxt) != 1: break
                prev, cur = cur, nxt[0]
            if len(nxt) >= 2 and len(path) <= spur:  # reached a junction: a spur
                for p in path: sk[p] = False
                changed = True
        if not changed: break
    return skeletonize(sk)


def text_boxes(y):
    """Boxes of the label text (< MIN_EXTENT yellow components, joined into words), extended left over the `T<n>=` prefix."""
    lab, _ = ndi.label(y, np.ones((3, 3)))
    glyph = np.zeros_like(y)
    for i, b in enumerate(ndi.find_objects(lab), 1):
        if max(b[0].stop-b[0].start, b[1].stop-b[1].start) < MIN_EXTENT: glyph[b] |= lab[b] == i
    words, _ = ndi.label(ndi.binary_dilation(glyph, np.ones((5, 15))))
    boxes = np.zeros_like(y)
    for b in ndi.find_objects(words):
        h = b[0].stop-b[0].start
        boxes[max(b[0].start-3, 0):b[0].stop+3, max(int(b[1].start-1.5*h), 0):b[1].stop+3] = True  # `T7=` may touch the line
    return boxes, glyph


def label_maps(gray, two_path, bottom, details=False):
    """(C, t, w): 1-px centerlines, soft target exp(-d^2/2 sigma^2), and the loss weight (0 = ignore) for one image."""
    y = yellow(two_path, bottom)
    boxes, glyph = text_boxes(y)
    lab, _ = ndi.label(y, np.ones((3, 3)))
    keep = np.zeros_like(y)
    for i, b in enumerate(ndi.find_objects(lab), 1):
        if max(b[0].stop-b[0].start, b[1].stop-b[1].start) >= MIN_EXTENT: keep[b] |= lab[b] == i
    C = prune(skeletonize(keep))
    d = ndi.distance_transform_edt(~C)
    t = np.exp(-d**2/(2*SIGMA**2)).astype(np.float32)
    f = gray.astype(np.float32)/255
    f = f-ndi.gaussian_filter(f, 40)
    R = np.max([sato(f, sigmas=[s], black_ridges=False) for s in (1.5, 3, 6, 10)], 0)   # fixed pixel scales: bundles at every magnification
    med = np.median(R)
    mad = 1.4826*np.median(np.abs(R-med))
    sm = ndi.gaussian_filter(gray.astype(np.float32), 3)
    ignore = (ndi.binary_dilation((R > med+3*mad) | (sm > threshold_otsu(sm)), iterations=5) | boxes) & (d > 3*SIGMA)
    w = np.where(ignore, 0, 1).astype(np.float32)
    return (C, t, w, dict(ignore=ignore, glyph=glyph & ~C, boxes=boxes)) if details else (C, t, w)


def tips(C):
    lab, n = ndi.label(C, np.ones((3, 3)))
    nb = ndi.convolve(C.astype(int), np.ones((3, 3)), mode='constant')-1
    return [int(((lab == i) & C & (nb == 1)).sum()) for i in range(1, n+1)]


def build_samples(folders=('CNT/261103', 'CNT/261105'), cache=True):
    """List of dicts name, folder, mag, bin, x (normalised gray), t, w, C. Cached in validation/cnt-learn/samples.npz."""
    file = OUT/'samples.npz'
    if cache and file.is_file():
        z = np.load(file, allow_pickle=False)
        return [dict(name=str(n), folder=str(f), mag=float(m), bin=mag_bin(float(m)), x=z[f'x{i}'].astype(np.float32), t=z[f't{i}'].astype(np.float32),
                     w=z[f'w{i}'].astype(np.float32), C=z[f'C{i}']) for i, (n, f, m) in enumerate(zip(z['names'], z['folders'], z['mags']))]
    samples = []
    for folder in folders:
        images, _ = discover([ROOT/folder], 0, set())    # discover applies `eligible`
        for image in images:
            g = luminance(image['base'])
            bottom = detect_information_footer(g)
            gray = g[:bottom]
            C, t, w = label_maps(gray, image['two'], bottom)
            samples.append(dict(name=image['base'].stem, folder=folder, mag=image['mag'], bin=mag_bin(image['mag']), x=cnt_detect.normalise_gray(gray), t=t, w=w, C=C))
    assert len({s['name'] for s in samples}) == len(samples), 'stems must be unique: they key folds and oof maps'
    if cache:
        OUT.mkdir(parents=True, exist_ok=True)
        arrays = {}
        for i, s in enumerate(samples): arrays.update({f'x{i}': s['x'].astype(np.float16), f't{i}': s['t'].astype(np.float16), f'w{i}': s['w'].astype(np.uint8), f'C{i}': s['C']})
        np.savez(file, names=[s['name'] for s in samples], folders=[s['folder'] for s in samples], mags=[s['mag'] for s in samples], **arrays)
    return samples


def make_folds(samples, k=5, seed=0):
    """Image-level folds stratified by magnification bin and folder, balanced across folds; written once to folds.json."""
    file = OUT/'folds.json'
    rng = np.random.default_rng(seed)
    folds, counter = {}, 0
    for b in BINS:
        group = sorted([s for s in samples if s['bin'] == b], key=lambda s: (s['folder'], rng.random()))
        for s in group:
            folds[s['name']] = counter % k; counter += 1
    OUT.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(folds, indent=1, sort_keys=True), encoding='utf-8')
    return folds


def load_folds(samples):
    file = OUT/'folds.json'
    return json.loads(file.read_text(encoding='utf-8')) if file.is_file() else make_folds(samples)


def render(gray, C, t, w, ignore, glyph, path):
    g = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB).astype(np.float32)
    o = g.copy()
    o[ignore] = o[ignore]*.55+np.array([0, 90, 255])*.45          # ignore: blue
    band = (t > np.exp(-4.5)) & (w > 0)
    o[band] = o[band]*.5+np.array([255, 0, 0])*.5                   # d <= 3 sigma: red
    o[C] = (255, 255, 0)                                            # centerline: yellow
    o[glyph] = (255, 0, 255)                                        # glyph pixels not in C: magenta
    Image.fromarray(np.hstack([g, o]).clip(0, 255).astype(np.uint8)).save(path)


def overlays(names=('CNT_powder_1kx-12', 'CNT_powder_500x-1', 'CNT_powder_100x-12', 'CNT_powder_2000x-8', 'CNT_powder_1kx-5', 'CNT_powder_200x-3')):
    (OUT/'labels').mkdir(parents=True, exist_ok=True)
    images, _ = discover([ROOT/'CNT/261103', ROOT/'CNT/261105'], 0, set())
    for image in images:
        if image['base'].stem not in names: continue
        g = luminance(image['base'])
        bottom = detect_information_footer(g)
        gray = g[:bottom]
        C, t, w, d = label_maps(gray, image['two'], bottom, details=True)
        render(gray, C, t, w, d['ignore'], d['glyph'], OUT/'labels'/f"{image['base'].stem}.png")
        print(f"{image['base'].stem}: ignore {100*d['ignore'].mean():.1f}%  tips/component {tips(C)}  skeleton px {int(C.sum())}", flush=True)


# ---------------------------------------------------------------- model and training (D3)

def torch_modules():
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    return torch, nn, F


def make_unet():
    torch, nn, F = torch_modules()

    def block(i, o):
        return nn.Sequential(nn.Conv2d(i, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True),
                             nn.Conv2d(o, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True))

    class UNet(nn.Module):
        """1 input channel, 4 levels 16-32-64-128, bilinear up + skip concat; outputs logits."""
        def __init__(self, c=(16, 32, 64, 128)):
            super().__init__()
            self.down = nn.ModuleList([block(1 if i == 0 else c[i-1], c[i]) for i in range(len(c))])
            self.up = nn.ModuleList([block(c[i]+c[i+1], c[i]) for i in range(len(c)-1)])
            self.head = nn.Conv2d(c[0], 1, 1)

        def forward(self, x):
            skips = []
            for i, d in enumerate(self.down):
                x = d(x if i == 0 else F.max_pool2d(x, 2)); skips.append(x)
            for i in reversed(range(len(self.up))):
                x = self.up[i](torch.cat([skips[i], F.interpolate(x, scale_factor=2, mode='bilinear', align_corners=False)], 1))
            return self.head(x)

    return UNet()


def sample_patch(s, rng):
    """One augmented 256x256 (x, t, w): geometric warp applied to all three, photometric to x only."""
    h, w_ = s['x'].shape
    if len(s['pos']) and rng.random() < .7:
        cy, cx = s['pos'][rng.integers(len(s['pos']))]+rng.uniform(-40, 40, 2)
    else:
        cy, cx = rng.uniform(0, h), rng.uniform(0, w_)
    cy, cx = np.clip(cy, 0, h-1), np.clip(cx, 0, w_-1)
    a, sc = rng.uniform(0, 2*np.pi), rng.uniform(.7, 1.4)
    A = sc*np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    if rng.random() < .5: A = A@np.diag([-1., 1.])
    o = np.array([(PATCH-1)/2, (PATCH-1)/2])
    M = np.hstack([A, (o-A@np.array([cx, cy]))[:, None]]).astype(np.float64)
    warp = lambda img, mode, val=0: cv2.warpAffine(img, M, (PATCH, PATCH), flags=cv2.INTER_LINEAR, borderMode=mode, borderValue=val)
    x = warp(s['x'], cv2.BORDER_REFLECT_101)
    t, w = warp(s['t'], cv2.BORDER_CONSTANT), warp(s['w'], cv2.BORDER_CONSTANT)   # outside the image: ignored
    x = np.clip(x, 0, 1)**rng.uniform(.7, 1.4)
    x = (x-.5)*rng.uniform(.8, 1.25)+.5
    if rng.random() < .3: x = cv2.GaussianBlur(x, (0, 0), rng.uniform(.01, 1.0))
    x = x+rng.normal(0, rng.uniform(.01, .05), x.shape).astype(np.float32)
    if rng.random() < .3: x = x+rng.normal(0, .02, (PATCH, 1)).astype(np.float32)           # SEM line noise
    if rng.random() < .3:                                                                   # charging gradient, +-15 %
        phi = rng.uniform(0, 2*np.pi)
        yy, xx = np.mgrid[-1:1:PATCH*1j, -1:1:PATCH*1j]
        x = x*(1+rng.uniform(-.15, .15)*(np.cos(phi)*xx+np.sin(phi)*yy)).astype(np.float32)
    return np.clip(x, 0, 1).astype(np.float32), t.astype(np.float32), w.astype(np.float32)


def val_patches(samples, rng, n=16):
    """Fixed, unaugmented crops of the 3 validation images (one per bin): a diagnostic, not used for stopping."""
    out = []
    for s in samples:
        for _ in range(n):
            if len(s['pos']) and rng.random() < .5: cy, cx = s['pos'][rng.integers(len(s['pos']))]
            else: cy, cx = rng.uniform(0, s['x'].shape[0]), rng.uniform(0, s['x'].shape[1])
            y0 = int(np.clip(cy-PATCH//2, 0, max(s['x'].shape[0]-PATCH, 0))); x0 = int(np.clip(cx-PATCH//2, 0, max(s['x'].shape[1]-PATCH, 0)))
            out.append(tuple(a[y0:y0+PATCH, x0:x0+PATCH] for a in (s['x'], s['t'], s['w'])))
    return out


def train(samples, names, epochs=24, patches=1024, threads=8, seed=0, log=print):
    torch, nn, F = torch_modules()
    torch.set_num_threads(threads); torch.manual_seed(seed); cv2.setNumThreads(1)
    rng = np.random.default_rng(seed)
    pool = [dict(s, pos=np.argwhere(s['C'])) for s in samples if s['name'] in names]
    # validation images (held in, diagnostic only): one per magnification bin
    check = [next(s for s in sorted(pool, key=lambda s: rng.random()) if s['bin'] == b) for b in BINS if any(s['bin'] == b for s in pool)]
    vx = val_patches(check, np.random.default_rng(1234))
    pos_weight = float(np.clip(sum((s['w']*(1-s['t'])).sum() for s in pool)/max(sum((s['w']*s['t']).sum() for s in pool), 1), 1, 100))
    log(f'train images {len(pool)}, validation images {[s["name"] for s in check]}, pos_weight {pos_weight:.1f}')
    model = make_unet().to(memory_format=torch.channels_last)
    steps = epochs*(patches//16)
    opt = torch.optim.AdamW(model.parameters(), 2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, steps)
    pw = torch.tensor(pos_weight)

    def loss_fn(z, t, w):
        bce = (F.binary_cross_entropy_with_logits(z, t, pos_weight=pw, reduction='none')*w).sum()/w.sum().clamp(min=1)
        p = torch.sigmoid(z)
        dice = 1-2*(w*p*t).sum()/(w*(p+t)).sum().clamp(min=1e-6)    # soft Dice on w > 0 pixels
        return bce+dice, bce

    def tensors(batch):
        return [torch.from_numpy(np.stack(a)[:, None]).contiguous(memory_format=torch.channels_last) for a in zip(*batch)]

    started = time.time()
    for epoch in range(1, epochs+1):
        model.train(); losses = []
        for _ in range(patches//16):
            x, t, w = tensors([sample_patch(pool[rng.integers(len(pool))], rng) for _ in range(16)])
            loss, _ = loss_fn(model(x), t, w)
            opt.zero_grad(); loss.backward(); opt.step(); sched.step()
            losses.append(float(loss))
        model.eval()
        with torch.no_grad():
            x, t, w = tensors(vx)
            vb = float(loss_fn(model(x), t, w)[1])
        log(f'epoch {epoch}/{epochs} train loss {np.mean(losses):.4f} val wBCE {vb:.4f} lr {sched.get_last_lr()[0]:.5f} elapsed {time.time()-started:.0f}s')
    return model


def export(model, xml_path):
    torch, nn, _ = torch_modules()
    import openvino as ov
    xml_path = Path(xml_path); xml_path.parent.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), OUT/('final.pt' if xml_path == FINAL_XML else xml_path.with_suffix('.pt').name))   # not next to the shipped xml
    net = nn.Sequential(model.to(memory_format=torch.contiguous_format), nn.Sigmoid()).eval()
    ov.save_model(ov.convert_model(net, example_input=torch.zeros(1, 1, 768, 1024), input=[(1, 1, -1, -1)]), str(xml_path), compress_to_fp16=True)


def xml_for(fold):
    return FINAL_XML if fold == 'final' else OUT/f'fold{fold}.xml'


def run_fold(fold, epochs, patches, threads, seed):
    samples = build_samples()
    folds = load_folds(samples)
    names = {s['name'] for s in samples if fold == 'final' or folds[s['name']] != int(fold)}
    OUT.mkdir(parents=True, exist_ok=True)
    logfile = open(OUT/f'train_{fold}.log', 'a', encoding='utf-8')

    def log(msg):
        line = f'{time.strftime("%H:%M:%S")} [{fold}] {msg}'
        print(line, flush=True); logfile.write(line+'\n'); logfile.flush()

    log(f'start: {len(names)} of {len(samples)} images, epochs {epochs}, patches {patches}, threads {threads}')
    model = train(samples, names, epochs, patches, threads, seed+(100 if fold == 'final' else int(fold)), log)
    export(model, xml_for(fold))
    log(f'saved {xml_for(fold)}')


def run_all(epochs, patches, threads, seed):
    samples = build_samples()
    load_folds(samples)
    master = open(OUT/'train.log', 'a', encoding='utf-8')
    for wave in (['0', '1', '2'], ['3', '4', 'final']):
        started = time.time()
        procs = [subprocess.Popen([sys.executable, __file__, '--fold', f, '--epochs', str(epochs), '--patches', str(patches), '--threads', str(threads), '--seed', str(seed)],
                                  stdout=subprocess.DEVNULL, stderr=open(OUT/f'train_{f}.err', 'w')) for f in wave]
        for f, p in zip(wave, procs):
            code = p.wait()
            master.write(f'{time.strftime("%H:%M:%S")} fold {f} exit {code}\n'); master.flush()
        master.write(f'{time.strftime("%H:%M:%S")} wave {wave} done in {time.time()-started:.0f}s\n'); master.flush()


def run_oof():
    samples = build_samples()
    folds = load_folds(samples)
    (OUT/'oof').mkdir(parents=True, exist_ok=True)
    for image in discover([ROOT/'CNT/261103', ROOT/'CNT/261105'], 0, set())[0]:
        g = luminance(image['base'])
        gray = g[:detect_information_footer(g)]
        P = cnt_detect.centerline_map(gray, xml_for(folds[image['base'].stem]))
        assert P is not None, f"fold model for {image['base'].stem} did not load"
        np.save(OUT/'oof'/f"{image['base'].stem}.npy", P.astype(np.float16))
        print(image['base'].stem, 'fold', folds[image['base'].stem], flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fold', help='0..4 or final')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--oof', action='store_true')
    ap.add_argument('--overlays', action='store_true')
    ap.add_argument('--epochs', type=int, default=24)
    ap.add_argument('--patches', type=int, default=1024)
    ap.add_argument('--threads', type=int, default=8)
    ap.add_argument('--seed', type=int, default=0)
    a = ap.parse_args()
    if a.overlays: overlays()
    if a.fold is not None: run_fold(a.fold, a.epochs, a.patches, a.threads, a.seed)
    if a.all: run_all(a.epochs, a.patches, a.threads, a.seed)
    if a.oof: run_oof()


if __name__ == '__main__':
    main()
