#!/bin/bash
# status.sh — 一条命令看清整个系统状态
# 用法：bash status.sh

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { printf "  ${GREEN}✓${NC} %s\n" "$1"; }
bad()  { printf "  ${RED}✗${NC} %s\n" "$1"; }
warn() { printf "  ${YELLOW}!${NC} %s\n" "$1"; }
line() { echo "  ────────────────────────────────────────"; }

echo "================================================"
echo "  豆包免费服务器 · 系统状态"
echo "================================================"

echo
echo "[中转机服务]"
# 判定 systemd 可用性：list-units 能执行即可（is-system-running 在 degraded 状态也返回非0）
HAS_SYSTEMD=0
if command -v systemctl >/dev/null 2>&1 && systemctl list-units --no-pager >/dev/null 2>&1; then
  HAS_SYSTEMD=1
fi

for s in frps nginx moin-unified moin-renew moin-loginguard doubao-keepalive moin-autorecover; do
  if [ "$HAS_SYSTEMD" = "1" ]; then
    ST=$(systemctl is-active "$s" 2>/dev/null)
  else
    ST="n/a"
  fi
  if [ "$ST" = "active" ]; then
    ok "$s 运行中"
  elif [ "$ST" = "n/a" ]; then
    warn "$s (无 systemd，按进程检查)"
    # 按启动脚本名匹配
    case "$s" in
      moin-unified)     PAT="unified.py" ;;
      moin-renew)       PAT="renew-activator.py" ;;
      moin-loginguard)  PAT="login-guard.py" ;;
      doubao-keepalive) PAT="ka_v13.py" ;;
      moin-autorecover) PAT="autorecover.py" ;;
      *)                PAT="$s" ;;
    esac
    pgrep -f "$PAT" >/dev/null 2>&1 && ok "  进程存在" || bad "  进程不存在"
  else
    bad "$s 状态: ${ST:-未知}"
  fi
done

echo
echo "[监听端口]"
for p in 7000 80 18800 17800 18090; do
  if ss -tln 2>/dev/null | grep -q ":$p "; then
    ok "$p 监听中"
  else
    warn "$p 未监听（沙箱离线时正常）"
  fi
done

echo
echo "[登录状态]"
if command -v curl >/dev/null 2>&1; then
  ST=$(curl -s -m 5 http://127.0.0.1:18800/state 2>/dev/null)
  if echo "$ST" | grep -q '"logged": true'; then
    ok "豆包已登录"
  else
    warn "豆包未登录，需扫码: http://<中转机IP>:18800/"
  fi
fi

echo
echo "[沙箱隧道]"
if curl -s -m 5 http://127.0.0.1:17800/ping 2>/dev/null | grep -q '"ok"'; then
  ok "沙箱在线"
  curl -s -m 5 http://127.0.0.1:17800/health 2>/dev/null | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    for c in d.get('checks',[]):
        s='✓' if c['ok'] else '✗'
        print(f'  {s} {c[\"name\"]}: {c[\"detail\"]}')
except Exception: pass
" 2>/dev/null
else
  warn "沙箱离线（未完成部署或已回收）"
fi

echo
echo "[最近日志]"
for f in /root/keepalive.log /root/renew.log /root/login_guard.log; do
  [ -f "$f" ] || continue
  echo "  $(basename $f):"
  tail -2 "$f" | sed 's/^/    /'
done

echo
echo "================================================"
echo "  完整文档: docs/TROUBLESHOOTING.md"
echo "  自测命令: bash test.sh"
echo "================================================"
