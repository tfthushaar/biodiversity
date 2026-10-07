# Third-party notices

This project's own code is Apache-2.0 (see ../LICENSE). It uses the following third-party
works, each under its own licence.

## MegaDetector V6 (`MDV6-mit-yolov9-c`) model weights

Microsoft AI for Good Lab. Weights: <https://zenodo.org/records/15398270>. Project:
<https://github.com/microsoft/MegaDetector>. A converted ONNX copy of these weights is used for
inference (see ../docs/models.md).

MIT License

Copyright (c) Microsoft Corporation.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## YOLO (MIT implementation), used only offline to convert the weights to ONNX

<https://github.com/MultimediaTechLab/YOLO>. Not a runtime dependency.

MIT License

Copyright (c) 2024 Kin-Yiu, Wong and Hao-Tang, Tsui

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## DINOv2 ViT-S/14 backbone

Meta Platforms, Inc. and affiliates. Weights via `timm`:
<https://huggingface.co/timm/vit_small_patch14_dinov2.lvd142m>. Apache License 2.0
(<https://www.apache.org/licenses/LICENSE-2.0>). A converted ONNX copy is used for inference.

## Training photos for the plant classifier

iNaturalist photos licensed CC0, CC BY, CC BY-NC, CC BY-SA or CC BY-NC-SA, used only to train a
model; the photos themselves are not redistributed. Each photo's observation id, URL and licence
are listed in `docs/training/plants_manifest.jsonl`, so every contributor can be credited by
following the link. Photographer identities are deliberately not stored.

## Caltech Camera Traps (evaluation images, classifier training crops and test fixtures)

Beery, S., Van Horn, G., Perona, P. *Recognition in Terra Incognita*. ECCV 2018. Hosted by LILA BC:
<https://lila.science/datasets/caltech-camera-traps>. Community Data License Agreement,
permissive variant (CDLA-Permissive-1.0). Attribution is required.

## Occurrence data

iNaturalist observations and GBIF occurrence records keep the licence stated on each record
(stored in `media_items.license`). GRIIS checklists are CC BY 4.0. Reserve boundaries are
(c) OpenStreetMap contributors, ODbL 1.0.
