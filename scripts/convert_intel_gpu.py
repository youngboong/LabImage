"""Convert the unchanged official SAM2.1 Small weights for OpenVINO GPU."""
from pathlib import Path
import torch
import openvino as ov
from sam2.build_sam import build_sam2


class Encoder(torch.nn.Module):
    def __init__(self, model):
        super().__init__(); self.model = model
    def forward(self, image):
        out = self.model.forward_image(image)
        return tuple(out['backbone_fpn']) + tuple(out['vision_pos_enc'])


class Decoder(torch.nn.Module):
    def __init__(self, model):
        super().__init__(); self.decoder = model.sam_mask_decoder
    def forward(self, image, pe, sparse, dense, high0, high1):
        return self.decoder.predict_masks(image, pe, sparse, dense, True, [high0, high1])


def main():
    torch.set_num_threads(8)
    root = Path(__file__).resolve().parents[1]
    target = root/'checkpoints/openvino'; target.mkdir(exist_ok=True)
    model = build_sam2('configs/sam2.1/sam2.1_hiera_s.yaml', str(root/'checkpoints/sam2.1_hiera_small.pt'), device='cpu', apply_postprocessing=False)
    with torch.inference_mode():
        if not (target/'encoder.xml').exists():
            print('Converting encoder...', flush=True)
            converted = ov.convert_model(Encoder(model).eval(), example_input=torch.zeros(1,3,1024,1024), input=[(1,3,1024,1024)])
            ov.save_model(converted, target/'encoder.xml')
        if not (target/'decoder.xml').exists():
            print('Converting decoder...', flush=True)
            example = (torch.zeros(1,256,64,64), model.sam_prompt_encoder.get_dense_pe(), torch.zeros(1,2,256), torch.zeros(1,256,64,64), torch.zeros(1,32,256,256), torch.zeros(1,64,128,128))
            shapes = [(1,256,64,64),(1,256,64,64),(-1,-1,256),(-1,256,64,64),(1,32,256,256),(1,64,128,128)]
            converted = ov.convert_model(Decoder(model).eval(), example_input=example, input=shapes)
            ov.save_model(converted, target/'decoder.xml')
    print('Conversion complete', flush=True)


if __name__ == '__main__': main()
