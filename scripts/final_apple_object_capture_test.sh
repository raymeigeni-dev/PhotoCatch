#!/usr/bin/env bash
set -Eeuo pipefail

# One-shot local acceptance helper for the optional Apple Object Capture route.
# Does not overwrite the original video or change the current COLMAP endpoint.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== PhotoCatch Apple Object Capture local acceptance =="
echo "Repository: $ROOT"
echo "macOS: $(sw_vers -productVersion)"
echo "Architecture: $(uname -m)"
command -v swift >/dev/null || { echo "FAIL: Swift toolchain unavailable"; exit 2; }
command -v curl >/dev/null || { echo "FAIL: curl unavailable"; exit 2; }

VIDEO="${PHOTOCATCH_VIDEO:-}"
if [[ -z "$VIDEO" ]]; then
  for candidate in "$HOME/Desktop/PhotoCatch-test/IMG_0096.MOV" "$HOME/Desktop/PhotoCatch/IMG_0096.MOV" "$HOME/Desktop/IMG_0096.MOV"; do
    if [[ -f "$candidate" ]]; then VIDEO="$candidate"; break; fi
  done
fi

echo
echo "== 1/4 Build native helper =="
swift build -c release --package-path "$ROOT/native/apple-object-capture"
BIN="$ROOT/native/apple-object-capture/.build/release/photocatch-apple-capture"
[[ -x "$BIN" ]] || { echo "FAIL: native executable missing: $BIN"; exit 3; }

echo
echo "== 2/4 Probe native capability =="
PROBE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/photocatch-apple-probe.XXXXXX")"
trap 'rm -rf "$PROBE_DIR"' EXIT
mkdir -p "$PROBE_DIR/images"
# A blank image is only used to safely trigger a capability probe; it is not a reconstruction test.
python3 - "$PROBE_DIR/images/probe.jpg" <<'PY'
import sys
try:
    import cv2
    import numpy as np
    cv2.imwrite(sys.argv[1], np.full((128, 128, 3), 127, dtype=np.uint8))
except Exception as e:
    print("Could not create probe image:", e, file=sys.stderr)
    raise SystemExit(1)
PY
set +e
"$BIN" "$PROBE_DIR/images" "$PROBE_DIR/probe.usdz" > "$PROBE_DIR/probe.json" 2>&1
PROBE_RC=$?
set -e
cat "$PROBE_DIR/probe.json"
if [[ "$PROBE_RC" -eq 2 ]]; then
  echo "BLOCKED: PhotogrammetrySession reports unsupported on this Mac."
  exit 4
fi

echo
echo "== 3/4 Verify backend route and health =="
BASE_URL="${PHOTOCATCH_BASE_URL:-http://127.0.0.1:5000}"
if ! curl --silent --show-error --fail "$BASE_URL/api/health"; then
  echo
  echo "BLOCKED: start the PhotoCatch Flask backend, then rerun this script."
  echo "Example: python backend/server.py"
  exit 5
fi
echo
python3 - "$BASE_URL" <<'PY'
import json, sys, urllib.error, urllib.request
url = sys.argv[1].rstrip("/") + "/api/video/reconstruct/apple"
req = urllib.request.Request(url, data=b"{}", headers={"Content-Type":"application/json"}, method="POST")
try:
    urllib.request.urlopen(req, timeout=10)
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8", "replace")
    if e.code != 400 or ("video" not in body.lower() and "视频" not in body):
        print(f"FAIL: endpoint returned unexpected HTTP {e.code}: {body}")
        raise SystemExit(1)
    print("PASS: Apple endpoint is registered and validates missing upload.")
PY

echo
echo "== 4/4 Real video reconstruction =="
if [[ -z "$VIDEO" || ! -f "$VIDEO" ]]; then
  echo "BUILD/API PASS; REAL VIDEO TEST NOT RUN."
  echo "Set PHOTOCATCH_VIDEO to the absolute path of IMG_0096.MOV and rerun."
  exit 6
fi
echo "Video: $VIDEO"
echo "This may take a long time and use substantial memory."
echo "The source video is read only; generated USDZ is retained under backend/instance/reconstructions."
set +e
curl --silent --show-error --fail-with-body \
  -F "video=@$VIDEO" \
  "$BASE_URL/api/video/reconstruct/apple"
RC=$?
set -e
echo
if [[ "$RC" -ne 0 ]]; then
  echo "FAIL: API request failed (curl exit $RC). Inspect Flask logs."
  exit "$RC"
fi
echo "Request returned HTTP success; inspect JSON success=true and open the model_url USDZ before accepting quality."
