"""Exercise repeated real GPU prompts and recover after an isolated worker crash."""
import json
import time
from pathlib import Path
import numpy as np
from PIL import Image
from sam_runtime import configure_device,build_runtime_model,inference_context
from sam2.sam2_image_predictor import SAM2ImagePredictor


def main():
    root=Path(__file__).resolve().parents[1]
    configure_device('intel-gpu')
    model=build_runtime_model('intel-gpu')
    assert model.intel_gpu_info['active_device']=='intel-gpu',model.intel_gpu_info
    predictor=SAM2ImagePredictor(model)
    image=np.array(Image.open(root/'LabImage-data/outputs/projects/image_30a3f4cab6b595f9/input/normalized.png').convert('RGB'))[:768]
    times=[]
    with inference_context('intel-gpu'):
        predictor.set_image(image)
        for index in range(100):
            count=[1,2,4,8,16][index%5]
            coords=np.array([[400+j%4,400+j//4] for j in range(count)],np.float32)
            labels=np.ones(count,np.int32)
            start=time.perf_counter()
            masks,scores,_=predictor.predict(point_coords=coords,point_labels=labels,multimask_output=True)
            times.append(time.perf_counter()-start)
            assert model.intel_gpu_info['active_device']=='intel-gpu'
        # Simulate a crashed/unresponsive GPU process without risking a driver fault.
        client=model._intel_gpu_worker
        client.process.terminate();client.process.join(timeout=3)
        start=time.perf_counter()
        masks,scores,_=predictor.predict(point_coords=np.array([[400,400]],np.float32),point_labels=np.array([1]),multimask_output=True)
        recovery=time.perf_counter()-start
        assert model.intel_gpu_info['active_device']=='cpu'
        assert np.isfinite(scores).all() and masks.any()
        masks2,scores2,_=predictor.predict(point_coords=np.array([[400,400]],np.float32),point_labels=np.array([1]),multimask_output=True)
        assert np.array_equal(masks,masks2)
    result=dict(passed=True,gpu_predictions=100,point_counts=[1,2,4,8,16],
        cached_click_median_seconds=float(np.median(times[5:])),recovery_seconds=recovery,
        cpu_after_worker_crash=True,gpu_info=model.intel_gpu_info)
    (root/'validation/gpu-recovery.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':
    main()
