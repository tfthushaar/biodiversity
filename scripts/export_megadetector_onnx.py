"""Export MegaDetector V6 (MIT, YOLOv9-c) to a self-contained ONNX file.

One-off: run it in a throwaway environment that has torch and the MIT `yolo` library
(MultimediaTechLab/YOLO). The application itself never needs them; see docs/models.md.

    python scripts/export_megadetector_onnx.py --ckpt MDV6-mit-yolov9-c.ckpt \
        --config config_v9s.yaml --out MDV6-mit-yolov9-c.onnx

Both inputs come from Zenodo (record 15398270 for the checkpoint, 15178680 for the config).
The ONNX graph includes the box decoding, so the runtime only does NMS and unletterboxing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
import yaml
from omegaconf import OmegaConf
from yolo import create_converter, create_model

# From Zenodo's file listing. Checked BEFORE loading: the loader unpickles the checkpoint,
# which can run arbitrary code, so we only open a file that is the one we expect.
EXPECTED_MD5 = "d8626ba22fccbd9c520e0deb19d721f7"
IMAGE_SIZE = 640
NUM_CLASSES = 3  # animal, person, vehicle


def md5(path: Path) -> str:
    h = hashlib.md5()  # noqa: S324 - integrity check against the publisher's checksum
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Exportable(torch.nn.Module):
    """Network + box decoding as one graph: image -> (class logits, xyxy boxes in 640px space).

    Reproduces yolo.utils.bounding_box_utils.Vec2Box exactly, using its own anchor grid.
    """

    def __init__(self, model: torch.nn.Module, converter) -> None:
        super().__init__()
        self.model = model.eval()
        self.register_buffer("anchor_grid", converter.anchor_grid.clone())
        self.register_buffer("scaler", converter.scaler.clone().float())

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        layers = self.model(x)["Main"]  # one (class, anchor, box) triple per detection scale
        cls = torch.cat([c.permute(0, 2, 3, 1).flatten(1, 2) for c, _, _ in layers], dim=1)
        box = torch.cat([b.permute(0, 2, 3, 1).flatten(1, 2) for _, _, b in layers], dim=1)
        lt, rb = (box * self.scaler.view(1, -1, 1)).chunk(2, dim=-1)
        return cls, torch.cat([self.anchor_grid - lt, self.anchor_grid + rb], dim=-1)


def assert_all_weights_loaded(model: torch.nn.Module, ckpt: Path) -> int:
    """The library only warns about missing or mismatched layers, which would leave them randomly
    initialised and produce a model that runs but is wrong. Refuse that outright."""
    raw = torch.load(ckpt, map_location="cpu", weights_only=False)
    weights = {k.removeprefix("model.model."): v for k, v in raw["state_dict"].items()}
    problems = []
    for key, tensor in model.model.state_dict().items():
        if key not in weights:
            problems.append(f"missing {key}")
        elif weights[key].shape != tensor.shape:
            problems.append(f"shape {key}")
        elif not torch.equal(weights[key], tensor):
            problems.append(f"value differs {key}")
    if problems:
        raise SystemExit(f"{len(problems)} weight problems, e.g. {problems[:5]}")
    return len(model.model.state_dict())


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--ckpt", type=Path, required=True)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    got = md5(args.ckpt)
    if got != EXPECTED_MD5:
        raise SystemExit(f"checkpoint MD5 {got} != expected {EXPECTED_MD5}; refusing to load it")

    cfg = OmegaConf.create(yaml.safe_load(args.config.read_text(encoding="utf-8")))
    cfg.image_size = [IMAGE_SIZE, IMAGE_SIZE]
    model = create_model(cfg.model, weight_path=args.ckpt, class_num=NUM_CLASSES).eval()
    n = assert_all_weights_loaded(model, args.ckpt)
    print(f"all {n} weight tensors loaded and verified")

    converter = create_converter(cfg.model.name, model, cfg.model.anchor, cfg.image_size, "cpu")
    wrapper = Exportable(model, converter).eval()

    dummy = torch.rand(1, 3, IMAGE_SIZE, IMAGE_SIZE)
    with torch.no_grad():
        ref_cls, ref_box = wrapper(dummy)
    print(f"anchors: {ref_cls.shape[1]}, classes: {ref_cls.shape[2]}")

    export_kwargs = dict(
        input_names=["images"], output_names=["cls_logits", "boxes"],
        dynamic_axes={"images": {0: "batch"}, "cls_logits": {0: "batch"}, "boxes": {0: "batch"}},
        opset_version=17,
    )
    try:
        torch.onnx.export(wrapper, dummy, str(args.out), dynamo=False, **export_kwargs)
    except TypeError:  # older torch without the `dynamo` switch
        torch.onnx.export(wrapper, dummy, str(args.out), **export_kwargs)

    # The exported graph must reproduce the PyTorch model, at a batch size we did not trace with.
    import onnxruntime as ort

    sess = ort.InferenceSession(str(args.out), providers=["CPUExecutionProvider"])
    batch = torch.rand(2, 3, IMAGE_SIZE, IMAGE_SIZE)
    with torch.no_grad():
        want_cls, want_box = wrapper(batch)
    got_cls, got_box = sess.run(None, {"images": batch.numpy()})
    d_cls = float(np.abs(got_cls - want_cls.numpy()).max())
    d_box = float(np.abs(got_box - want_box.numpy()).max())
    print(f"max abs difference vs PyTorch: logits {d_cls:.2e}, boxes {d_box:.2e} (batch of 2)")
    if d_cls > 1e-3 or d_box > 1e-2:
        raise SystemExit("ONNX output does not match PyTorch; not trusting this export")

    meta = {
        "name": "MDV6-mit-yolov9-c",
        "source": "https://zenodo.org/records/15398270 (Microsoft AI for Good Lab)",
        "license": "MIT",
        "classes": ["animal", "person", "vehicle"],
        "input": f"Bx3x{IMAGE_SIZE}x{IMAGE_SIZE} float32 RGB 0-1, grey (114) letterbox",
        "outputs": {
            "cls_logits": "(B, N, 3) raw logits",
            "boxes": "(B, N, 4) x1y1x2y2 in 640px space",
        },
        "checkpoint_md5": got,
        "onnx_sha256": sha256(args.out),
        "onnx_bytes": args.out.stat().st_size,
        "max_abs_diff": {"logits": d_cls, "boxes": d_box},
    }
    sidecar = args.out.with_suffix(".json")
    sidecar.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out} ({meta['onnx_bytes'] / 1e6:.1f} MB) and {sidecar.name}")


if __name__ == "__main__":
    main()
