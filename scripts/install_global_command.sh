#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
TARGET_DIR="${HOME}/.local/bin"
TARGET_CMD="${TARGET_DIR}/protocol_monk_checkout"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python || true)}"

mkdir -p "${TARGET_DIR}"

if [ -z "${PYTHON_BIN}" ]; then
  echo "Python interpreter not found on PATH." >&2
  exit 1
fi

cat > "${TARGET_CMD}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="__REPO_ROOT__"
PYTHON_BIN="__PYTHON_BIN__"

cd "${REPO_ROOT}"
exec "${PYTHON_BIN}" -m protocol_monk.main "$@"
EOF

python - <<PY
from pathlib import Path

path = Path("${TARGET_CMD}")
text = path.read_text(encoding="utf-8")
text = text.replace("__REPO_ROOT__", "${REPO_ROOT}")
text = text.replace("__PYTHON_BIN__", "${PYTHON_BIN}")
path.write_text(text, encoding="utf-8")
PY

chmod 755 "${TARGET_CMD}"

echo "Installed checkout-local helper: ${TARGET_CMD}"
echo "Preferred public install path: python -m pip install ."
if command -v protocol_monk_checkout >/dev/null 2>&1; then
  echo "Resolved helper path: $(command -v protocol_monk_checkout)"
else
  echo "protocol_monk_checkout is not on PATH yet. Ensure ${TARGET_DIR} is in your PATH."
fi
