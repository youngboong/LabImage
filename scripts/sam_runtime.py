"""Shared inference device selection for the editor and command-line analysis."""
from contextlib import contextmanager, nullcontext
import os

import torch


def select_device(requested='auto'):
    if requested not in ('auto', 'cpu', 'cuda', 'intel-gpu'):
        raise ValueError('Device must be auto, cpu, cuda, or intel-gpu.')
    if requested == 'cpu':
        return 'cpu'
    if requested in ('auto', 'intel-gpu'):
        from lab_openvino import available
        if available(): return 'intel-gpu'
        if requested == 'intel-gpu':
            raise ValueError('Intel GPU is unavailable. Check the Intel graphics driver and bundled OpenVINO models.')
    available = torch.cuda.is_available()
    if requested == 'cuda' and not available:
        raise ValueError('CUDA is unavailable. Use --device cpu or auto.')
    return 'cuda' if available else 'cpu'


def configure_device(requested='auto'):
    device = select_device(requested)
    if device in ('cpu', 'intel-gpu'):
        # Avoid excessive thread contention in interactive desktop use.
        torch.set_num_threads(min(torch.get_num_threads(), os.cpu_count() or 1, 8))
    return device


def build_runtime_model(device):
    from sam2.build_sam import build_sam2
    from app_paths import checkpoint_path
    model = build_sam2('configs/sam2.1/sam2.1_hiera_s.yaml', str(checkpoint_path()),
        device='cpu' if device == 'intel-gpu' else device, apply_postprocessing=False)
    if device == 'intel-gpu':
        from lab_openvino import accelerate
        model = accelerate(model)
    return model


@contextmanager
def inference_context(device):
    # CPU uses float32; CUDA autocast must never be entered on a CPU-only build.
    precision = nullcontext()
    if device == 'cuda':
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        precision = torch.autocast('cuda', dtype=dtype)
    with torch.inference_mode(), precision:
        yield


def release_device_cache(device):
    if device == 'cuda':
        torch.cuda.empty_cache()
