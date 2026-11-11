"""Intel GPU execution for SAM2's encoder and mask decoder; original prompts/API."""
from pathlib import Path
import hashlib
import types
import logging
import numpy as np
import torch


OFFICIAL_SHA256 = '6d1aa6f30de5c92224f8172114de081d104bbd23dd9dc5c58996f0cad5dc4d38'


def available():
    from app_paths import ASSET_ROOT
    if not (ASSET_ROOT/'checkpoints/openvino/decoder.xml').is_file(): return False
    try:
        import openvino as ov
        return 'GPU' in ov.Core().available_devices
    except Exception:
        return False


def accelerate(model):
    from app_paths import ASSET_ROOT, output_root, checkpoint_path
    from lab_gpu_worker import GPUWorker
    if hashlib.sha256(checkpoint_path().read_bytes()).hexdigest() != OFFICIAL_SHA256:
        raise ValueError('Intel GPU models require the bundled official SAM 2.1 Small checkpoint.')
    folder = ASSET_ROOT/'checkpoints/openvino'
    cache = output_root()/'.intel-gpu-cache-safe'; cache.mkdir(parents=True, exist_ok=True)
    original_forward = model.forward_image
    original_predict = model.sam_mask_decoder.predict_masks
    info = dict(active_device='intel-gpu')
    def fallback(error):
        info.update(active_device='cpu', fallback_reason=str(error),
            notice='Intel GPU stopped responding. Continuing on CPU; saved labels are preserved.')
        model.forward_image = original_forward
        model.sam_mask_decoder.predict_masks = original_predict
        logging.error('Intel GPU disabled for this session; CPU fallback: %s', error)
    model.intel_gpu_info = info
    try:
        client = GPUWorker(folder, cache)
        model._intel_gpu_worker = client
        info.update(client.info)
    except Exception as error:
        fallback(error)
        return model
    def arrays(tensors):
        return [np.ascontiguousarray(t.detach().cpu().float().numpy()) for t in tensors]
    image_key = None
    def forward_image(self, image):
        nonlocal image_key
        image_key = None
        try:
            values = [torch.from_numpy(value) for value in client.infer('encoder', arrays([image]))]
        except Exception as error:
            fallback(error)
            return original_forward(image)
        return dict(backbone_fpn=values[:3], vision_pos_enc=values[3:], vision_features=values[2])
    def predict_masks(self, image_embeddings, image_pe, sparse_prompt_embeddings,
                      dense_prompt_embeddings, repeat_image, high_res_features=None):
        nonlocal image_key
        if image_embeddings.shape[0] != 1:
            raise ValueError('Intel GPU image prediction expects one cached image.')
        try:
            # Exact independent predictions; avoid GPU allocations for a dynamic
            # prompt batch of 8+ during automatic labeling.
            outputs = []
            key = tuple(t.data_ptr() for t in [image_embeddings,*high_res_features])
            for index in range(sparse_prompt_embeddings.shape[0]):
                static = arrays([image_embeddings,image_pe,*high_res_features]) if key != image_key else None
                dense = dense_prompt_embeddings[index:index+1]
                if dense.stride(-1) == 0 and dense.stride(-2) == 0:
                    dense = dense[:,:,:1,:1]
                values = dict(image=static,prompts=arrays([sparse_prompt_embeddings[index:index+1],dense]))
                outputs.append(client.infer('decoder', values))
                image_key = key
            return tuple(torch.from_numpy(np.concatenate(items,axis=0)) for items in zip(*outputs))
        except Exception as error:
            fallback(error)
            return original_predict(image_embeddings, image_pe, sparse_prompt_embeddings,
                dense_prompt_embeddings, repeat_image, high_res_features)
    model.forward_image = types.MethodType(forward_image, model)
    model.sam_mask_decoder.predict_masks = types.MethodType(predict_masks, model.sam_mask_decoder)
    return model
