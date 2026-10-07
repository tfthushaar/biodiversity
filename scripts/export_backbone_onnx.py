"""Export the shared image backbone (DINOv2 ViT-S/14, Apache-2.0) to ONNX.

One-off, in a throwaway environment with torch and timm (see docs/models.md). The application
needs only onnxruntime.

    python scripts/export_backbone_onnx.py --out dinov2_vits14.onnx

The embedding is the CLS token joined to the mean of the patch tokens (768 numbers), the
combination DINOv2's authors recommend for linear classification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import timm
import torch

MODEL = "vit_small_patch14_dinov2.lvd142m"
SIZE = 224  # 16x16 patches of 14 px: 5x cheaper than the 518 px default, fine for CPU


class Embedding(torch.nn.Module):
    def __init__(self, model: torch.nn.Module) -> None:
        super().__init__()
        self.model = model
        self.prefix = model.num_prefix_tokens

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        tokens = self.model.forward_features(x)  # (B, prefix + patches, 384), already normed
        cls = tokens[:, 0]
        patches = tokens[:, self.prefix :].mean(dim=1)
        return torch.cat([cls, patches], dim=-1)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    model = timm.create_model(MODEL, pretrained=True, num_classes=0, img_size=SIZE).eval()
    cfg = timm.data.resolve_data_config({}, model=model)
    print("pretrained config:", {k: cfg[k] for k in ("mean", "std", "interpolation")})
    wrapper = Embedding(model).eval()

    dummy = torch.rand(1, 3, SIZE, SIZE)
    with torch.no_grad():
        want = wrapper(torch.rand(3, 3, SIZE, SIZE))
    print("embedding shape:", tuple(want.shape))

    kwargs = dict(input_names=["images"], output_names=["embedding"], opset_version=17,
                  dynamic_axes={"images": {0: "batch"}, "embedding": {0: "batch"}})
    try:
        torch.onnx.export(wrapper, dummy, str(args.out), dynamo=False, **kwargs)
    except TypeError:
        torch.onnx.export(wrapper, dummy, str(args.out), **kwargs)

    import onnxruntime as ort

    sess = ort.InferenceSession(str(args.out), providers=["CPUExecutionProvider"])
    batch = torch.rand(5, 3, SIZE, SIZE)  # a batch size different from the traced one
    with torch.no_grad():
        ref = wrapper(batch).numpy()
    got = sess.run(None, {"images": batch.numpy()})[0]
    diff = float(np.abs(got - ref).max())
    norms = np.linalg.norm(got, axis=1) * np.linalg.norm(ref, axis=1)
    cos = float(((got * ref).sum(axis=1) / norms).min())  # worst row
    print(f"max abs difference vs PyTorch: {diff:.2e}; worst cosine {cos:.6f}")
    if diff > 1e-3 or cos < 0.99999:
        raise SystemExit("ONNX output does not match PyTorch; not trusting this export")

    meta = {
        "name": "dinov2_vits14", "timm_model": MODEL,
        "source": "https://huggingface.co/timm/" + MODEL, "license": "Apache-2.0",
        "input": f"Bx3x{SIZE}x{SIZE} float32 RGB, ImageNet mean/std",
        "mean": list(cfg["mean"]), "std": list(cfg["std"]),
        "output": "embedding (B, 768) = [CLS token | mean of patch tokens]",
        "onnx_sha256": sha256(args.out), "onnx_bytes": args.out.stat().st_size,
        "max_abs_diff": diff,
    }
    sidecar = args.out.with_suffix(".json")
    sidecar.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out} ({meta['onnx_bytes'] / 1e6:.1f} MB) and {sidecar.name}")


if __name__ == "__main__":
    main()
