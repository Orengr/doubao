#!/bin/bash
# rotate-token.sh — 轮换 frp token（安全运维）
#
# 用法：bash rotate-token.sh
# 作用：生成新 token，更新 frps，并输出新的沙箱 frpc 配置
# 注意：轮换后需要让豆包重新执行沙箱部署指令

set -e
CONF=${CONF:-/root/frps.toml}
PEND=${PEND:-/home/user/.dsh_pend}
FRPS_ADDR=${FRPS_ADDR:-$(curl -s -m 5 https://api.ipify.org)}

NEW_TOKEN=$(openssl rand -base64 30 | tr -d '/+=' | head -c 32)
echo "[*] 新 token: $NEW_TOKEN"

# 更新 frps 配置
if [ -f "$CONF" ]; then
  sed -i "s|^auth.token = .*|auth.token = \"$NEW_TOKEN\"|" "$CONF"
  sed -i "s|^webServer.password = .*|webServer.password = \"${NEW_TOKEN:0:16}\"|" "$CONF"
  echo "[*] frps.toml 已更新"
fi

# 重启 frps
if command -v systemctl >/dev/null 2>&1 && systemctl is-system-running >/dev/null 2>&1; then
  systemctl restart frps
  echo "[*] frps 已重启"
else
  pkill -x frps 2>/dev/null || true
  sleep 1
  nohup frps -c "$CONF" >> /root/frps.log 2>&1 &
  echo "[*] frps 已用 nohup 重启"
fi

# 输出新的沙箱配置片段
cat > /root/NEW_FRPC_TOML <<TOML
serverAddr = "$FRPS_ADDR"
serverPort = 7000
auth.method = "token"
auth.token = "$NEW_TOKEN"

[[proxies]]
name = "dbp-ctl"
type = "tcp"
localIP = "127.0.0.1"
localPort = 17800
remotePort = 17800

[[proxies]]
name = "dbp-panel"
type = "tcp"
localIP = "127.0.0.1"
localPort = 18090
remotePort = 18090
TOML

echo
echo "=== 新的 frpc.toml 已生成: /root/NEW_FRPC_TOML ==="
echo "把内容发给豆包，让它更新 /home/user/.dsh_pend/frp/frpc.toml 并重启 frpc"
echo
echo "[!] 安全提示：不要把这个 token 贴到公开场合"
