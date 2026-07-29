#!/usr/bin/env bash
# 逐对检查 HoshinoBot 与 autopcr 的依赖约束能否共存于同一环境。
#
# 用法：scripts/verify_conflict.sh [HoshinoBot 目录] [autopcr 目录]
set -euo pipefail

HOSHINO_ROOT="${1:-../ref/HoshinoBot}"
AUTOPCR_ROOT="${2:-../ref/autopcr_latest}"
PYTHON="${PYTHON:-.venv-autopcr/bin/python}"

echo "== 同时求解两套约束 =="
if uv pip install --python "$PYTHON" --dry-run \
    -r "$HOSHINO_ROOT/requirements.txt" \
    -r "$AUTOPCR_ROOT/requirements.txt" >/dev/null 2>&1; then
    echo "  两套约束可以共存"
    exit 0
fi
echo "  无解，逐对定位："

# 取出两份清单中同名的包，比较各自的版本约束。
mapfile -t PAIRS < <(
    "$PYTHON" - "$HOSHINO_ROOT/requirements.txt" "$AUTOPCR_ROOT/requirements.txt" <<'PY'
import re, sys

def load(path):
    result = {}
    with open(path) as fp:
        for line in fp:
            line = line.split('#')[0].strip()
            if not line:
                continue
            match = re.match(r'^([A-Za-z0-9_.\-]+)(\[[^\]]*\])?(.*)$', line)
            if match:
                result[match.group(1).lower()] = line
    return result

left, right = load(sys.argv[1]), load(sys.argv[2])
for name in sorted(set(left) & set(right)):
    print(left[name] + '|' + right[name])
PY
)

for pair in "${PAIRS[@]}"; do
    a="${pair%%|*}"
    b="${pair##*|}"
    if uv pip install --python "$PYTHON" --dry-run "$a" "$b" >/dev/null 2>&1; then
        printf '  可共解  %-24s + %s\n' "$a" "$b"
    else
        printf '  冲突    %-24s + %s\n' "$a" "$b"
    fi
done
