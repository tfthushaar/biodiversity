"""Check that our ONNX + NumPy pipeline reproduces the reference implementation on real images.

Run in the export environment (needs torch and the MIT `yolo` library). It runs both pipelines
on the same photos and reports every disagreement, so "it looks right" is not the evidence.

    python scripts/verify_megadetector.py --ckpt X.ckpt --config Y.yaml --onnx Z.onnx \
        --images data/lila/caltech/images --limit 60 --confidence 0.2
"""

from __future__ import annotations

import argparse
from pathlib import Path

import torch
import yaml
from omegaconf import OmegaConf
from PIL import Image
from yolo import AugmentationComposer, PostProcess, create_converter, create_model

from biodiv.inference.megadetector import CLASS_NAMES, MegaDetector, visible_box

dropped = [0]  # reference detections lying outside the real image


def reference_detector(ckpt: Path, config: Path, confidence: float):
    cfg = OmegaConf.create(yaml.safe_load(config.read_text(encoding="utf-8")))
    cfg.image_size = [640, 640]
    cfg.task.nms.min_confidence = confidence
    model = create_model(cfg.model, weight_path=ckpt, class_num=3).eval()
    converter = create_converter(cfg.model.name, model, cfg.model.anchor, cfg.image_size, "cpu")
    post = PostProcess(converter, cfg.task.nms)
    transform = AugmentationComposer([], cfg.image_size, cfg.image_size[0])

    def run(image: Image.Image):
        tensor, _, rev = transform(image.convert("RGB"))
        with torch.no_grad():
            out = post(model(tensor[None]), rev[None])[0]
        w, h = image.size
        raw = [
            (CLASS_NAMES[int(r[0])], float(r[5]), (r[1] / w, r[2] / h, r[3] / w, r[4] / h))
            for r in out.tolist()
        ]
        kept = [(lab, c, vb) for lab, c, b in raw if (vb := visible_box(b)) is not None]
        dropped[0] += len(raw) - len(kept)
        return kept

    return run, float(cfg.task.nms.min_iou)


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--ckpt", type=Path, required=True)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--onnx", type=Path, required=True)
    p.add_argument("--images", type=Path, required=True)
    p.add_argument("--limit", type=int, default=60)
    p.add_argument("--confidence", type=float, default=0.2)
    args = p.parse_args()

    ref, ref_iou = reference_detector(args.ckpt, args.config, args.confidence)
    ours = MegaDetector(args.onnx, confidence=args.confidence, iou=ref_iou)
    print(f"reference NMS IoU = {ref_iou}; comparing at confidence {args.confidence}")

    files = sorted(args.images.glob("*.jpg"))[: args.limit]
    n_ref = n_ours = n_match = 0
    worst_box, worst_conf, mismatches = 0.0, 0.0, []
    for f in files:
        im = Image.open(f)
        a, b = ref(im), ours.detect(im)
        n_ref, n_ours = n_ref + len(a), n_ours + len(b)
        pool = list(b)
        for label, conf, box in a:
            best = max((d for d in pool if d.label == label), default=None,
                       key=lambda d: iou(d.box, box))
            if best and iou(best.box, box) > 0.95 and abs(best.confidence - conf) < 0.02:
                n_match += 1
                worst_box = max(worst_box, 1 - iou(best.box, box))
                worst_conf = max(worst_conf, abs(best.confidence - conf))
                pool.remove(best)
            else:
                got = best and round(best.confidence, 3)
                mismatches.append((f.name, label, round(conf, 3), got))
    print(f"reference detections discarded as outside the image: {dropped[0]}")
    print(f"images {len(files)}: reference {n_ref} detections, ours {n_ours}, matched {n_match}")
    print(f"worst box disagreement (1-IoU) {worst_box:.4f}, worst confidence gap {worst_conf:.4f}")
    for m in mismatches[:15]:
        print("  MISMATCH", m)
    if mismatches or n_ref != n_ours:
        raise SystemExit(f"{len(mismatches)} reference detections unmatched")
    print("OK: identical detections on every image")


if __name__ == "__main__":
    main()
