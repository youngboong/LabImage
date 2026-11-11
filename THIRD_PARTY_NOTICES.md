# Third-party notices

LabImage is derived from [youngboong/PoreSAM](https://github.com/youngboong/PoreSAM),
upstream commit dabb4f173ce3f41d4e4794ec2c12809dd2f0f6db, under Apache License 2.0.
The LICENSE file preserves its license. LabImage changes the workflows, general
object selection, measurement definitions, instance export, interface and model.

SAM 2 code and the official SAM 2.1 Small pretrained checkpoint are from
[Meta / facebookresearch/sam2](https://github.com/facebookresearch/sam2), under
Apache License 2.0; its connected-components implementation has a BSD license.
The checkpoint has not been fine-tuned for LabImage or for pores. Its source URL
and SHA-256 are recorded in checkpoints/default_model.json.

Other runtime dependencies retain their own licenses and notices in the
distribution's metadata and license directories. These include PyTorch,
TorchVision, NumPy, SciPy, scikit-image, OpenCV, Pillow, Matplotlib, pandas,
pywebview, Python.NET, Hydra and their dependencies.

OpenVINO 2025.4 runtime (Intel), Apache-2.0. Runtime licenses are bundled under _internal/licenses/OpenVINO. SAM2 OpenVINO conversion uses the original official Meta checkpoint; no training or quantization calibration data is used.
