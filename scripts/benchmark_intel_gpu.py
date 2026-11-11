"""Real image encoder and cached point predictions: CPU versus Intel GPU."""
import json
import time
from pathlib import Path
import numpy as np
from PIL import Image
from sam_runtime import configure_device, build_runtime_model, inference_context
from sam2.sam2_image_predictor import SAM2ImagePredictor


def run():
    root = Path(__file__).resolve().parents[1]
    image = np.array(Image.open(root/'validation/release-waypoint-backend/sample.png').convert('RGB'))
    results = {}; reference = None
    for requested in ('cpu', 'intel-gpu'):
        device = configure_device(requested)
        start = time.perf_counter(); model = build_runtime_model(device)
        results[device] = dict(load_seconds=time.perf_counter()-start, gpu_info=getattr(model,'intel_gpu_info',None))
        predictor = SAM2ImagePredictor(model)
        with inference_context(device):
            start = time.perf_counter(); predictor.set_image(image)
            results[device]['encode_seconds'] = time.perf_counter()-start
            times = []; final = None
            for _ in range(6):
                start = time.perf_counter()
                masks, scores, _ = predictor.predict(point_coords=np.array([[90,100]],np.float32),point_labels=np.array([1]),multimask_output=True)
                times.append(time.perf_counter()-start); final=masks[np.argmax(scores)].astype(bool)
            results[device].update(first_click_seconds=times[0], cached_click_median_seconds=float(np.median(times[1:])), mask_pixels=int(final.sum()), scores=scores.tolist())
            if reference is None: reference=final
            else: results[device]['cpu_mask_iou'] = float((reference&final).sum()/(reference|final).sum())
        print(device, results[device],flush=True)
        del predictor, model
    (root/'validation/intel-benchmark.json').write_text(json.dumps(results,indent=2),encoding='utf-8')


if __name__=='__main__': run()

