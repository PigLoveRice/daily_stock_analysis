#!/usr/bin/env bash
# apply_stock_list_from_serenity.sh
#
# 一键把 serenity 7/2 daily run 产出的 90 只候选灌进 DSA 的 STOCK_LIST。
# 数据源: /home/serenity-bottleneck/data/dsa_import_batches.json
#
# 用法:
#   bash scripts/apply_stock_list_from_serenity.sh         # 合并(保留现有自选)
#   bash scripts/apply_stock_list_from_serenity.sh --reset # 用 serenity 全量替换
#   bash scripts/apply_stock_list_from_serenity.sh --dry  # 只预览,不写
#
# 注意: 本脚本直接编辑 /home/daily_stock_analysis/.env。
# 改完后需重启 DSA 进程(systemctl restart daily-stock-analysis)
# 或等下次自然 reload,DSA 才会感知新的 STOCK_LIST。

set -euo pipefail

ENV_FILE="/home/daily_stock_analysis/.env"
BATCHES="/home/serenity-bottleneck/data/dsa_import_batches.json"
BACKUP_DIR="/home/daily_stock-analysis/data/stock_list_backups"
TS=$(date +%Y%m%d_%H%M%S)

MODE="merge"
[[ "${1:-}" == "--reset" ]] && MODE="reset"
[[ "${1:-}" == "--dry" ]] && MODE="dry"

# 1. 读取 serenity 候选(去重 + 归一化 600309.SH → 600309)
python3 - "$BATCHES" "$MODE" <<'PY'
import json, sys, re
batches_path, mode = sys.argv[1], sys.argv[2]
with open(batches_path) as f:
    batches = json.load(f)
seen = set()
codes = []
for b in batches:
    for c in b["codes"]:
        n = c.split(".")[0]  # 600309.SH -> 600309
        if n not in seen:
            seen.add(n)
            codes.append(n)
print(f"serenity 候选去重后: {len(codes)} 只, mode={mode}")
with open("/tmp/serenity_codes.txt", "w") as f:
    f.write("\n".join(codes))
PY

mapfile -t SERENITY_CODES < /tmp/serenity_codes.txt
echo "==> 主题分布:"
python3 -c "
import json
b = json.load(open('$BATCHES'))
for x in sorted(b, key=lambda y: -y['count']):
    print(f\"  {x['theme']:<32} {x['count']:>3} 只\")
"

# 2. 读现有 STOCK_LIST
EXISTING=$(grep -E '^STOCK_LIST=' "$ENV_FILE" | head -1 | cut -d= -f2-)
EXISTING_CODES=()
[[ -n "$EXISTING" ]] && IFS=',' read -ra EXISTING_CODES <<< "$EXISTING"
echo ""
echo "==> 当前 STOCK_LIST: ${#EXISTING_CODES[@]} 只"

# 3. 合并/重置
if [[ "$MODE" == "reset" ]]; then
    NEW_CODES=("${SERENITY_CODES[@]}")
    echo "==> 模式: reset (用 serenity 全量替换)"
else
    NEW_CODES=("${EXISTING_CODES[@]}")
    for c in "${SERENITY_CODES[@]}"; do
        if [[ ! " ${NEW_CODES[*]} " =~ " $c " ]]; then
            NEW_CODES+=("$c")
        fi
    done
    echo "==> 模式: merge (保留现有,追加 serenity)"
fi
echo "==> 合并后: ${#NEW_CODES[@]} 只"

if [[ "$MODE" == "dry" ]]; then
    echo "==> DRY RUN: 不会修改 $ENV_FILE"
    echo "==> 预览前 5 只: ${NEW_CODES[@]:0:5}"
    exit 0
fi

# 4. 备份 + 写
mkdir -p "$BACKUP_DIR"
cp "$ENV_FILE" "$BACKUP_DIR/env.backup.$TS"
echo "==> 备份: $BACKUP_DIR/env.backup.$TS"

NEW_VALUE=$(IFS=,; echo "${NEW_CODES[*]}")
python3 -c "
import re, sys
p = '$ENV_FILE'
content = open(p).read()
new = re.sub(r'^STOCK_LIST=.*$', f'STOCK_LIST=$NEW_VALUE', content, flags=re.M)
open(p, 'w').write(new)
print(f'已更新 {p}')
"

# 5. 校验
VERIFY=$(grep -E '^STOCK_LIST=' "$ENV_FILE" | head -1 | cut -d= -f2-)
IFS=',' read -ra VERIFY_CODES <<< "$VERIFY"
echo "==> 回读校验: ${#VERIFY_CODES[@]} 只"

# 6. 提示
echo ""
echo "⚠️  重要: .env 改完后 DSA server 不会自动 reload。需重启:"
echo "   pkill -f 'python3 main.py --schedule --serve' && cd $ENV_FILE/.. && nohup python3 main.py --schedule --serve > /tmp/dsa.log 2>&1 &"
echo "   或在 DSA WebUI → 系统配置 → 触发 reload"
