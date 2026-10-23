#!/usr/bin/env bash
set -Eeuo pipefail

# Install the official OpenMVS v2.4.0 macOS arm64 release into the user's home.
# The upstream archive is checksum-pinned; no sudo and no system files are modified.
VERSION="2.4.0"
URL="https://github.com/cdcseacave/openMVS/releases/download/v2.4.0/OpenMVS_macOS_arm64.zip"
SHA256="3d4c616c97031b1ab6e2eecb0ddd5614fb99513c0782a32c9350602faf38799b"
BASE="${HOME}/.local/opt/openmvs-${VERSION}"
BIN="${HOME}/.local/bin"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "This installer is only for Apple Silicon macOS (arm64)." >&2
  exit 1
fi

mkdir -p "$BIN" "${HOME}/.local/opt"
echo "Downloading official OpenMVS ${VERSION} macOS arm64 archive..."
curl -fL --retry 3 "$URL" -o "$TMP/openmvs.zip"
echo "${SHA256}  $TMP/openmvs.zip" | shasum -a 256 -c -

mkdir -p "$TMP/unpacked"
ditto -x -k "$TMP/openmvs.zip" "$TMP/unpacked"
# Locate required tools without assuming a particular directory layout inside the zip.
for tool in InterfaceCOLMAP DensifyPointCloud ReconstructMesh; do
  found="$(find "$TMP/unpacked" -type f -name "$tool" -perm -111 -print -quit)"
  if [[ -z "$found" ]]; then
    echo "Official archive did not contain executable $tool; refusing partial installation." >&2
    find "$TMP/unpacked" -maxdepth 4 -type f -print >&2
    exit 1
  fi
done

rm -rf "$BASE"
mkdir -p "$BASE"
ditto "$TMP/unpacked" "$BASE"

for tool in InterfaceCOLMAP DensifyPointCloud ReconstructMesh; do
  found="$(find "$BASE" -type f -name "$tool" -perm -111 -print -quit)"
  ln -sfn "$found" "$BIN/$tool"
done

echo
echo "Installed OpenMVS tools:"
for tool in InterfaceCOLMAP DensifyPointCloud ReconstructMesh; do
  "$BIN/$tool" --help >/dev/null 2>&1 || true
  echo "$BIN/$tool -> $(readlink "$BIN/$tool")"
done
echo
echo "Installation files: $BASE"
echo "Add this to your shell PATH if needed:"
echo '  export PATH="$HOME/.local/bin:$PATH"'
echo "IMPORTANT: This verifies the official archive checksum and executable presence only."
echo "A real PhotoCatch reconstruction must still be run and its output inspected."
