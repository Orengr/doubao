#!/bin/sh
# ensure.sh — 沙箱恢复入口（幂等，可反复执行）
# 当前架构：Moin Agent + MySQL + PHP + frpc（1Panel/宝塔已移除）
PEND="${PEND:-/home/user/.dsh_pend}"
LOG="$PEND/log"
mkdir -p "$LOG" "$PEND/state" "$PEND/bin"
exec >> "$LOG/ensure.log" 2>&1
echo "===== $(date '+%F %T') ensure start ====="

SUDO=""
if sudo -n true 2>/dev/null; then SUDO="sudo"; fi

# ---------- 1. 面板 Agent (17802) ----------
if [ -f "$PEND/bin/sbx_agent.py" ]; then
  PIDF="$PEND/state/agent.pid"
  RUNNING=0
  if [ -f "$PIDF" ]; then
    OLD=$(cat "$PIDF" 2>/dev/null)
    [ -n "$OLD" ] && kill -0 "$OLD" 2>/dev/null && RUNNING=1
  fi
  if [ "$RUNNING" = "0" ]; then
    cd "$PEND" && setsid nohup python3 bin/sbx_agent.py >> "$LOG/sbx_agent.log" 2>&1 < /dev/null &
    echo $! > "$PIDF"
    sleep 2
    echo "[1] agent 已启动"
  else
    echo "[1] agent 已在运行"
  fi
else
  echo "[1] 警告: bin/sbx_agent.py 不存在"
fi

# ---------- 2. MySQL ----------
if [ -f "$PEND/bin/start_mysql.sh" ]; then
  sh "$PEND/bin/start_mysql.sh" 2>&1 | tail -2
  echo "[2] MySQL 检查完成"
fi

# ---------- 3. frpc 隧道 ----------
if [ -x "$PEND/frp/frpc" ] && [ -f "$PEND/frp/frpc.toml" ]; then
  if ! pgrep -x frpc >/dev/null 2>&1; then
    cd "$PEND/frp" && setsid nohup ./frpc -c frpc.toml >> "$LOG/frpc.log" 2>&1 < /dev/null &
    echo "[3] frpc 已启动"
  else
    echo "[3] frpc 已在运行"
  fi
fi

# ---------- 4. nginx ----------
if ! pgrep -x nginx >/dev/null 2>&1; then
  $SUDO nginx 2>/dev/null && echo "[4] nginx 已启动" || echo "[4] nginx 启动失败"
fi

# ---------- 5. supervisord 托管项（如果存在） ----------
SUPCTL=""
for c in supervisorctl /usr/bin/supervisorctl; do
  command -v "$c" >/dev/null 2>&1 && SUPCTL="$c" && break
done
if [ -n "$SUPCTL" ] && pgrep -x supervisord >/dev/null 2>&1; then
  if [ -f "$PEND/conf/dbp.conf" ]; then
    for d in /opt/gem/supervisord /etc/supervisord.d /etc/supervisor/conf.d /runtime/supervisord; do
      if [ -d "$d" ]; then
        $SUDO cp "$PEND/conf/dbp.conf" "$d/dbp.conf" 2>/dev/null
        break
      fi
    done
    $SUDO "$SUPCTL" reread 2>&1 | tail -1
    $SUDO "$SUPCTL" update 2>&1 | tail -1
    echo "[5] supervisord 已同步"
  fi
else
  echo "[5] supervisord 不可用，跳过"
fi

# ---------- 6. 自检 ----------
sleep 3
echo "[6] === 自检 ==="
TOK=$(cat "$PEND/state/token.txt" 2>/dev/null)
AGENT_OK=$(curl -s -m 3 "http://127.0.0.1:17802/api/ping?token=${TOK}" 2>/dev/null | grep -c ok)
echo "  agent:   $([ "$AGENT_OK" -gt 0 ] && echo 运行中 || echo 未运行)"
echo "  frpc:    $(pgrep -x frpc >/dev/null && echo 运行中 || echo 未运行)"
echo "  mysql:   $(pgrep -x mysqld >/dev/null && echo 运行中 || echo 未运行)"
echo "  nginx:   $(pgrep -x nginx >/dev/null && echo 运行中 || echo 未运行)"
echo "  host:    $(uname -n)"
echo "===== $(date '+%F %T') ensure done ====="
