#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/Users/nicholaspitzarella/Desktop/protocol_event_build"
CONDA_SH="/opt/miniconda3/etc/profile.d/conda.sh"
ENV_NAME="monk_env"
TARGET_DIR="${HOME}/.local/bin"
TARGET_CMD="${TARGET_DIR}/protocol_monk"

if [ ! -d "${REPO_ROOT}" ]; then
  echo "Repository root not found: ${REPO_ROOT}" >&2
  exit 1
fi

if [ ! -f "${CONDA_SH}" ]; then
  echo "Conda activation script not found: ${CONDA_SH}" >&2
  exit 1
fi

mkdir -p "${TARGET_DIR}"

cat > "${TARGET_CMD}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/Users/nicholaspitzarella/Desktop/protocol_event_build"
CONDA_SH="/opt/miniconda3/etc/profile.d/conda.sh"
ENV_NAME="monk_env"

if [ ! -f "${CONDA_SH}" ]; then
  echo "Conda activation script not found: ${CONDA_SH}" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${CONDA_SH}"
conda activate "${ENV_NAME}"

cd "${REPO_ROOT}"
exec python -m protocol_monk.main "$@"
EOF

chmod 755 "${TARGET_CMD}"

echo "Installed global command: ${TARGET_CMD}"
if command -v protocol_monk >/dev/null 2>&1; then
  echo "Resolved command path: $(command -v protocol_monk)"
else
  echo "protocol_monk is not on PATH yet. Ensure ${TARGET_DIR} is in your PATH."
fi
