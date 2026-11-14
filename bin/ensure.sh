#!/bin/sh
# ensure.sh — 沙箱恢复入口（幂等，可反复执行）
#
# 作用：把 supervisord 配置装回去，拉起所有托管进程，重启 frpc
#
# 环境变量：
#   PEND          持久目录（默认 /home/user/.dsh_pend）
#   CTL_PORT      控制面端口（默认 17800）
#   SUP_DIR       自定义 supervisord 配置目录（默认自动探测）
#
PEND="${PEND:-/home/user/.dsh_pend}"
CTL_PORT="${CTL_PORT:-17800}"
LOG="$PEND/log"
mkdir -p "$LOG"
exec >> "$LOG/ensure.log" 2>&1
echo "===== $(date '+%F %T') ensure start ====="

SUDO=""
if sudo -n true 2>/dev/null; then SUDO="sudo"; fi

# ---------- 自动探测 supervisord 配置目录 ----------
detect_sup_dir() {
  # 1. 显式指定优先
  if [ -n "${SUP_DIR:-}" ] && [ -d "$SUP_DIR" ]; then
    echo "$SUP_DIR"; return 0
  fi
  # 2. 常见路径探测（按命中顺序）
  for d in \
    /opt/gem/supervisord \
    /etc/supervisord.d \
    /etc/supervisor/conf.d \
    /opt/supervisord \
    /runtime/supervisord
  do
    if [ -d "$d" ]; then
      echo "$d"; return 0
    fi
  done
  # 3. 从运行中的 supervisord 反推
  SUP_PID=$(pgrep -x supervisord 2>/dev/null | head -1)
  if [ -n "$SUP_PID" ]; then
    for f in /proc/$SUP_PID/cmdline; do
      [ -r "$f" ] || continue
      CMD=$(tr '\0' ' ' < "$f" 2>/dev/null)
      # 从 -c /path/to/supervisord.conf 提取目录
      case "$CMD" in
        *-c*)
          CONF=$(echo "$CMD" | sed -n 's/.*-c[[:space:]]*\([^[:space:]]*\).*/\1/p')
          if [ -n "$CONF" ] && [ -f "$CONF" ]; then
            BASEDIR=$(dirname "$CONF")
            # 看主配置里的 include 路径
            INC=$(grep -E '^\s*files\s*=' "$CONF" 2>/dev/null | tail -1 | sed 's/.*=\s*//')
            if [ -n "$INC" ]; then
              D=$(dirname "$INC")
              [ -d "$D" ] && { echo "$D"; return 0; }
            fi
            [ -d "$BASEDIR/supervisord" ] && { echo "$BASEDIR/supervisord"; return 0; }
          fi
          ;;
      esac
    done
  fi
  # 4. 兜底
  echo "/opt/gem/supervisord"
}

# ---------- 找到 supervisorctl ----------
find_supervisorctl() {
  for c in supervisorctl /usr/bin/supervisorctl /usr/local/bin/supervisorctl; do
    if command -v "$c" >/dev/null 2>&1; then
      echo "$c"; return 0
    fi
  done
  echo ""
}

SUP_DIR_DETECTED=$(detect_sup_dir)
SUPCTL=$(find_supervisorctl)
echo "[0] supervisord 配置目录: $SUP_DIR_DETECTED"
echo "[0] supervisorctl: ${SUPCTL:-未找到}"

# ---------- 1. 部署 supervisord 配置 ----------
# 关键：只有在 supervisord 确实存在时才部署，避免创建无用目录
SUP_AVAILABLE=0
if [ -n "$SUPCTL" ] && pgrep -x supervisord >/dev/null 2>&1; then
  SUP_AVAILABLE=1
fi

if [ "$SUP_AVAILABLE" = "1" ]; then
  if [ -f "$PEND/conf/dbp.conf" ]; then
    $SUDO mkdir -p "$SUP_DIR_DETECTED" 2>/dev/null
    $SUDO cp "$PEND/conf/dbp.conf" "$SUP_DIR_DETECTED/dbp.conf" 2>/dev/null \
      && echo "[1] dbp.conf 已部署到 $SUP_DIR_DETECTED" \
      || echo "[1] 警告：dbp.conf 部署失败"
  else
    echo "[1] 警告: $PEND/conf/dbp.conf 不存在"
  fi
else
  echo "[1] supervisord 不可用，跳过托管配置（将使用直接启动兜底）"
  SUPCTL=""   # 后续步骤也跳过 supervisorctl
fi

# ---------- 2. 重载 supervisord ----------
if [ -n "$SUPCTL" ]; then
  $SUDO "$SUPCTL" reread 2>&1 | tail -3
  $SUDO "$SUPCTL" update 2>&1 | tail -3
  sleep 5

  # ---------- 3. 确保关键进程运行 ----------
  for prog in dbp-ctl dbp-1panel dbp-frpc dbp-watch; do
    ST=$($SUDO "$SUPCTL" status "$prog" 2>/dev/null | awk '{print $2}')
    if [ "$ST" != "RUNNING" ]; then
      echo "[3] 启动 $prog (当前: ${ST:-未注册})"
      $SUDO "$SUPCTL" start "$prog" 2>&1 | tail -1
    fi
  done
else
  echo "[2-3] supervisorctl 不可用，跳过托管"
fi

# ---------- 4. 直接兜底启动（supervisord 失效时） ----------
if [ -x "$PEND/frp/frpc" ] && [ -f "$PEND/frp/frpc.toml" ]; then
  if ! pgrep -x frpc >/dev/null 2>&1; then
    cd "$PEND/frp" || exit 1
    nohup ./frpc -c frpc.toml >> "$LOG/frpc.log" 2>&1 &
    echo "[4] frpc 已直接启动"
  fi
fi

# 控制面兜底
if ! pgrep -f "dbp-ctl.py" >/dev/null 2>&1; then
  if [ -x "$PEND/bin/dbp-ctl.py" ] || [ -f "$PEND/bin/dbp-ctl.py" ]; then
    cd "$PEND" || exit 1
    PEND="$PEND" CTL_PORT="$CTL_PORT" nohup python3 bin/dbp-ctl.py >> "$LOG/ctl.log" 2>&1 &
    echo "[4] dbp-ctl 已直接启动"
  fi
fi

# 看护兜底
if ! pgrep -f "dbp-watch.py" >/dev/null 2>&1; then
  if [ -f "$PEND/bin/dbp-watch.py" ]; then
    cd "$PEND" || exit 1
    PEND="$PEND" CTL_PORT="$CTL_PORT" nohup python3 bin/dbp-watch.py >> "$LOG/watch.log" 2>&1 &
    echo "[4] dbp-watch 已直接启动"
  fi
fi

# ---------- 4.5 注册 1Panel（成品包解压后） ----------
if [ -x "$PEND/1panel/1panel" ]; then
  mkdir -p "$PEND/1panel-data"
  $SUDO cp "$PEND/1panel/1panel" /usr/local/bin/1panel 2>/dev/null
  $SUDO cp "$PEND/1panel/1pctl" /usr/local/bin/1pctl 2>/dev/null
  $SUDO chmod +x /usr/local/bin/1panel /usr/local/bin/1pctl 2>/dev/null
  if [ -f /usr/local/bin/1pctl ]; then
    $SUDO sed -i "s|^BASE_DIR=.*|BASE_DIR=$PEND/1panel-data|" /usr/local/bin/1pctl 2>/dev/null
    echo "[4.5] 1Panel 已注册（数据目录 $PEND/1panel-data）"
  fi
fi

# ---------- 5. 自检 ----------
sleep 8
echo "[5] === 自检 ==="
echo "  控制面: $(curl -s -m 4 "http://127.0.0.1:${CTL_PORT}/ping" | head -c 100)"
echo "  1Panel:  $(curl -s -m 4 -o /dev/null -w '%{http_code}' "http://127.0.0.1:18090/" 2>/dev/null)"
echo "  frpc:    $(pgrep -x frpc >/dev/null && echo 运行中 || echo 未运行)"
echo "  进程:"
ps -eo pid,comm 2>/dev/null | grep -E 'frpc|python3' | head -5 | sed 's/^/    /'
if [ -n "$SUPCTL" ]; then
  $SUDO "$SUPCTL" status 2>&1 | grep dbp- | head -6 | sed 's/^/    /'
fi
echo "===== ensure done ====="
