#!/usr/bin/env bash
# Download the ONNX models from the GitHub release into data/models/.
#
# Used by the Render build. It NEVER fails the build: if the release does not exist yet, the
# service still deploys and the photo-analysis endpoints report themselves unavailable.
set -u
base="${MODELS_URL:-https://github.com/tfthushaar/biodiversity/releases/download/models-v1}"
dest="${MODELS_DIR:-data/models}"
mkdir -p "$dest"
for f in MDV6-mit-yolov9-c.onnx MDV6-mit-yolov9-c.json dinov2_vits14.onnx dinov2_vits14.json; do
  if curl -fsSL -o "$dest/$f" "$base/$f"; then
    echo "fetched $f"
  else
    rm -f "$dest/$f"
    echo "not available yet: $f"
  fi
done
exit 0
