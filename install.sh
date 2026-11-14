#!/bin/bash
# install.sh — 一键部署（在中转机执行，生成发给豆包的指令）
#
# 用法：
#   bash install.sh
#
# 需要修改下面 3 个变量（或通过环境变量传入）
set -e

# 优先读取同目录 config.env（用户首次配置的材料）
CFG="$(cd "$(dirname "$0")" && pwd)/config.env"
if [ -f "$CFG" ]; then
  # 只读取 KEY=VALUE 行，不执行任意代码
  while IFS='=' read -r k v; do
    case "$k" in
      FRPS_ADDR|DOMAIN|PANEL_SUBDOMAIN|CTL_PORT|PANEL_PORT|WEB_PORT|\
      PANEL_USER|PANEL_PASS|FRPS_TOKEN|CF_DOMAIN)
        # 环境变量优先，其次 config.env
        if [ -z "$(eval echo \${$k:-})" ]; then
          export "$k=$v"
        fi
        ;;
    esac
  done < <(grep -E '^[A-Z_]+=' "$CFG" 2>/dev/null)
fi

FRPS_ADDR="${FRPS_ADDR:-}"
FRPS_TOKEN="${FRPS_TOKEN:-}"
# 组件/二进制统一从 GitHub 拉取（用户 clone 即用，不依赖中转机预置）
GITHUB_RAW="${GITHUB_RAW:-https://raw.githubusercontent.com/Orengr/doubao/main}"
PANEL_PORT="${PANEL_PORT:-18090}"
CTL_PORT="${CTL_PORT:-17800}"
WEB_PORT="${WEB_PORT:-18800}"
PANEL_USER="${PANEL_USER:-admin}"
PANEL_PASS="${PANEL_PASS:-123456}"
DOMAIN="${DOMAIN:-}"
CF_DOMAIN="${CF_DOMAIN:-}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

# 检测 systemd 是否可用（很多免费容器没有）
HAS_SYSTEMD=0
if command -v systemctl >/dev/null 2>&1 && systemctl is-system-running >/dev/null 2>&1; then
  HAS_SYSTEMD=1
fi
if [ "$HAS_SYSTEMD" = "0" ]; then
  printf "${YELLOW}[!]${NC} 未检测到 systemd，将使用 nohup 直接启动服务\n"
fi
say() { printf "${GREEN}[+]${NC} %s\n" "$1"; }
warn() { printf "${YELLOW}[!]${NC} %s\n" "$1"; }
err() { printf "${RED}[x]${NC} %s\n" "$1"; }

echo "================================================"
echo "  豆包免费服务器 · 一键部署"
echo "================================================"
echo

# ---------- 0. 先汇报材料清单 ----------
echo "[准备材料] 部署前请确认已备齐："
echo "  1. 一台有公网 IP 的 Linux 机器（1核512M，是你自己的中转机）"
echo "  2. 一个豆包账号"
echo "  3. 首次扫一次码（30 秒）"
echo "  不需要：域名 / 备案 / 信用卡 / 手机 root / ADB"
echo "  完整清单见: $(cd "$(dirname "$0")" && pwd)/PREPARE.md"
echo "------------------------------------------------"
# 非交互模式下不阻塞；交互模式给一次确认机会
if [ -t 0 ] && [ -z "${FRPS_ADDR:-}" ]; then
  read -r -p "材料已备齐？[Y/n] " CONFIRM
  case "${CONFIRM:-Y}" in
    [Nn]*) echo "请先准备材料，再见"; exit 0 ;;
  esac
fi
echo

# ---------- 1. 环境检查 ----------
say "检查环境"
if [ "$(id -u)" != "0" ]; then
  err "请用 root 运行"
  exit 1
fi

for c in curl tar python3; do
  command -v $c >/dev/null || { err "缺少 $c"; exit 1; }
done
say "基础工具齐全"

# ---------- 2. 收集配置 ----------
if [ -z "$FRPS_ADDR" ]; then
  PUBIP=$(curl -s -m 5 https://api.ipify.org || echo "")
  echo
  echo "请输入中转机的公网地址（frps 所在机器）"
  echo "  当前检测到: ${PUBIP:-未知}"
  read -r -p "FRPS_ADDR [${PUBIP}]: " INPUT
  FRPS_ADDR="${INPUT:-$PUBIP}"
fi
[ -z "$FRPS_ADDR" ] && { err "必须提供 FRPS_ADDR"; exit 1; }

if [ -z "$FRPS_TOKEN" ]; then
  FRPS_TOKEN=$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)
  say "已生成 frp token"
fi

say "中转机: $FRPS_ADDR"
say "控制面端口: $CTL_PORT"
say "1Panel 端口: $PANEL_PORT"

# ---------- 3. 部署 frps ----------
say "部署 frps"

# 关键：如果已有配置，保留原 token，避免破坏已连接沙箱
if [ -f /root/frps.toml ]; then
  OLD_TOKEN=$(grep -E '^auth\.token' /root/frps.toml 2>/dev/null | sed 's/.*=\s*"//;s/"//')
  if [ -n "$OLD_TOKEN" ] && [ -z "${FRPS_TOKEN_OVERRIDE:-}" ]; then
    if [ "$OLD_TOKEN" != "$FRPS_TOKEN" ]; then
      warn "检测到已有 frps 配置，保留原 token（如需更换请设 FRPS_TOKEN_OVERRIDE=1）"
      FRPS_TOKEN="$OLD_TOKEN"
    else
      say "已有配置，token 一致"
    fi
  fi
fi
if command -v frps >/dev/null 2>&1; then
  say "frps 已存在，跳过下载"
elif true; then
  FRP_VER="0.72.0"
  cd /tmp
  curl -fsSL -o frp.tar.gz \
    "https://ghfast.top/https://github.com/fatedier/frp/releases/download/v${FRP_VER}/frp_${FRP_VER}_linux_amd64.tar.gz" \
    || curl -fsSL -o frp.tar.gz \
      "https://github.com/fatedier/frp/releases/download/v${FRP_VER}/frp_${FRP_VER}_linux_amd64.tar.gz"
  tar xzf frp.tar.gz
  cp frp_${FRP_VER}_linux_amd64/frps /usr/local/bin/
  chmod +x /usr/local/bin/frps
fi
FRP_VER_SHOW=$(frps --version 2>&1 | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
say "frps ${FRP_VER_SHOW:-已安装}"

cat > /root/frps.toml <<EOF
bindPort = 7000

auth.method = "token"
auth.token = "${FRPS_TOKEN}"

webServer.addr = "127.0.0.1"
webServer.port = 7501
webServer.user = "admin"
webServer.password = "${FRPS_TOKEN:0:16}"

log.to = "/root/frps.log"
log.level = "info"
log.maxDays = 7

allowPorts = [
  { start = ${CTL_PORT}, end = $((CTL_PORT + 2)) },
  { start = ${PANEL_PORT}, end = $((PANEL_PORT + 2)) }
]

# 安全：只允许指定端口，避免 token 泄露后被注册任意端口
# frps 0.72 支持 maxPortsPerClient
maxPortsPerClient = 4
EOF

cat > /etc/systemd/system/frps.service <<'EOF'
[Unit]
Description=frp server
After=network-online.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/frps -c /root/frps.toml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

if [ "$HAS_SYSTEMD" = "1" ]; then
  systemctl daemon-reload
  systemctl enable --now frps 2>/dev/null || systemctl restart frps
  sleep 2
  systemctl is-active frps >/dev/null && say "frps 已启动（systemd）" || warn "frps systemd 启动异常"
else
  # 无 systemd：nohup 直接启动
  pkill -x frps 2>/dev/null || true
  sleep 1
  nohup frps -c /root/frps.toml >> /root/frps.log 2>&1 &
  sleep 3
  if pgrep -x frps >/dev/null; then
    say "frps 已启动（nohup）"
  else
    err "frps 启动失败"
    tail -5 /root/frps.log
    exit 1
  fi
fi

# ---------- 4. 部署 nginx 分流 ----------
if command -v nginx >/dev/null; then
  say "配置 nginx 分流"
  # 备份原配置
  [ -f /etc/nginx/sites-available/dbp ] && \
    cp /etc/nginx/sites-available/dbp /etc/nginx/sites-available/dbp.bak.$(date +%s) 2>/dev/null
  cat > /etc/nginx/sites-available/dbp <<EOF
server {
    listen 80 default_server;
    server_name _;

    location /panel/ {
        proxy_pass http://127.0.0.1:${PANEL_PORT}/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 600s;
        proxy_buffering off;
        client_max_body_size 100m;
    }

    location / {
        proxy_pass http://127.0.0.1:${CTL_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 300s;
        proxy_buffering off;
        client_max_body_size 20m;
    }
}
EOF
  mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
  ln -sf /etc/nginx/sites-available/dbp /etc/nginx/sites-enabled/dbp
  # 只在存在默认站点时移除
  [ -f /etc/nginx/sites-enabled/default ] && rm -f /etc/nginx/sites-enabled/default
  if nginx -t 2>&1 | grep -q successful; then
    systemctl reload nginx && say "nginx 已配置"
  else
    err "nginx 配置有误："
    nginx -t 2>&1 | tail -3
    warn "跳过 nginx，可直接用端口访问"
  fi
fi

# ---------- 5. 打包沙箱所需文件 ----------
say "打包沙箱组件"

# 关键优化：把大文件预下载到中转机，沙箱走内网拉取
# 原版让沙箱从 GitHub 下载 frp(14MB) + 1Panel(47MB)，耗时且吃额度
PKG_BLOBS=/var/www/html/dbp/blobs
mkdir -p "$PKG_BLOBS"

# 关键：优先用仓库自带 bt_res/ 的离线资源（用户 clone 后就有，零下载）
REPO_RES="$(cd "$(dirname "$0")" && pwd)/bt_res"

# 5.1 frp 客户端（14MB）
if [ -f "$REPO_RES/frp.tar.gz" ]; then
  cp "$REPO_RES/frp.tar.gz" "$PKG_BLOBS/frp.tar.gz"
  say "frp: 使用仓库自带离线包 ✓"
elif [ ! -f "$PKG_BLOBS/frp.tar.gz" ]; then
  say "预下载 frp 客户端（一次性，约 14MB）"
  curl -fsSL -o "$PKG_BLOBS/frp.tar.gz" \
    "https://ghfast.top/https://github.com/fatedier/frp/releases/download/v0.72.0/frp_0.72.0_linux_amd64.tar.gz" \
    || curl -fsSL -o "$PKG_BLOBS/frp.tar.gz" \
      "https://github.com/fatedier/frp/releases/download/v0.72.0/frp_0.72.0_linux_amd64.tar.gz" \
    || warn "frp 预下载失败，沙箱将自行下载（回退）"
fi
[ -f "$PKG_BLOBS/frp.tar.gz" ] && say "frp: $(stat -c%s "$PKG_BLOBS/frp.tar.gz") 字节"

# 5.2 1Panel（47MB，可选）
if [ -f "$REPO_RES/1panel.tar.gz" ]; then
  cp "$REPO_RES/1panel.tar.gz" "$PKG_BLOBS/1panel.tar.gz"
  say "1Panel: 使用仓库自带离线包 ✓"
elif [ ! -f "$PKG_BLOBS/1panel.tar.gz" ]; then
  say "预下载 1Panel（一次性，约 47MB）"
  curl -fsSL --max-time 180 -o "$PKG_BLOBS/1panel.tar.gz" \
    "https://resource.fit2cloud.com/1panel/package/stable/v1.10.34-lts/release/1panel-v1.10.34-lts-linux-amd64.tar.gz" \
    || warn "1Panel 预下载失败，沙箱将自行下载（回退）"
fi
[ -f "$PKG_BLOBS/1panel.tar.gz" ] && say "1Panel: $(stat -c%s "$PKG_BLOBS/1panel.tar.gz") 字节"

chmod 644 "$PKG_BLOBS"/* 2>/dev/null || true

# 把必要的脚本和配置打包
TMPPKG=/tmp/dbp-pkg
rm -rf "$TMPPKG"; mkdir -p "$TMPPKG"
cp -r bin conf web "$TMPPKG/" 2>/dev/null
# 清理不需要的
rm -f "$TMPPKG/bin/unified.py" "$TMPPKG/bin/login-guard.py" 2>/dev/null
cd "$TMPPKG"
tar czf /tmp/dbp-pkg.tar.gz .
PKG_B64=$(base64 -w0 /tmp/dbp-pkg.tar.gz)
PKG_SIZE=$(stat -c%s /tmp/dbp-pkg.tar.gz)
say "组件包大小: ${PKG_SIZE} 字节"

# 启动一个临时 HTTP 服务供沙箱下载
PKG_DIR=/var/www/html/dbp
mkdir -p "$PKG_DIR"
cp /tmp/dbp-pkg.tar.gz "$PKG_DIR/pkg.tar.gz"
chmod 644 "$PKG_DIR/pkg.tar.gz"
say "组件包已放到 http://${FRPS_ADDR}/dl/dbp/pkg.tar.gz"

# nginx 加下载路径
if command -v nginx >/dev/null && [ -f /etc/nginx/sites-available/dbp ]; then
  if ! grep -q 'location /dl/' /etc/nginx/sites-available/dbp; then
    sed -i 's|    location / {|    location /dl/ {\n        alias /var/www/html/;\n        autoindex off;\n    }\n\n    location / {|' /etc/nginx/sites-available/dbp
    nginx -t 2>/dev/null && systemctl reload nginx && say "下载路径已配置"
  fi
fi

# ---------- 6. 生成沙箱部署指令 ----------
say "生成沙箱部署指令"
B64_TOKEN=$(printf '%s' "$FRPS_TOKEN" | base64 -w0)

# 生成沙箱指令（用 python 写文件，避免 heredoc 嵌套问题）
python3 - "$FRPS_ADDR" "$FRPS_TOKEN" "$CTL_PORT" "$PANEL_PORT" > /root/SANDBOX_CMDS.txt <<'PYEOF'
import sys
addr, token, ctl, panel = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
puser, ppass = sys.argv[5], sys.argv[6]
raw = sys.argv[7]
rel = "https://github.com/Orengr/doubao/releases/download/v2.0/doubao-bundle.tar.gz"

inner = f"""#!/bin/bash
# 豆包沙箱 · 成品包一步部署（下载解压即用，零公网安装）
set -e
PEND=/home/user/.dsh_pend
mkdir -p $PEND/log $PEND/state $PEND/tasks
cd /tmp

echo "[1/4] 下载成品包（约 58MB，含全部二进制）"
dl() {{
  local url="$1" dst="$2" min="$3"
  for i in 1 2 3; do
    curl -sL --max-time 300 -o "$dst" "$url" 2>/dev/null
    local sz=$(stat -c%s "$dst" 2>/dev/null || echo 0)
    if [ "$sz" -ge "$min" ] && tar tzf "$dst" >/dev/null 2>&1; then
      echo "    下载OK: $sz 字节 (第${{i}}次)"; return 0
    fi
    echo "    第${{i}}次不完整($sz)，重试…"; sleep 2
  done
  return 1
}}
dl "https://github.com/Orengr/doubao/releases/download/v2.0/doubao-bundle.tar.gz" bundle.tar.gz 50000000 || \
dl "{raw}/bt_res/doubao-bundle.tar.gz" bundle.tar.gz 50000000 || \
dl "{raw}/pkg.tar.gz" bundle.tar.gz 10000 || {{
  echo "成品包下载失败，请检查 GitHub 地址"; exit 1
}}

echo "[2/4] 解压到持久卷（解压即用，不用再装）"
tar xzf bundle.tar.gz -C /tmp
B=/tmp/doubao-bundle
[ -d "$B" ] || B=/tmp/dbp-x
for d in bin conf web frp 1panel; do
  [ -d "$B/$d" ] && cp -rf "$B/$d" $PEND/ 2>/dev/null || true
done
chmod +x $PEND/bin/*.sh $PEND/bin/*.py $PEND/frp/frpc $PEND/1panel/1panel $PEND/1panel/1pctl 2>/dev/null || true
echo "    bin: $(ls $PEND/bin | wc -l) 个脚本"
echo "    frpc: $(stat -c%s $PEND/frp/frpc 2>/dev/null || echo 0) 字节"
echo "    1panel: $(stat -c%s $PEND/1panel/1panel 2>/dev/null || echo 0) 字节"

echo "[3/4] 写 frpc 配置"
cat > $PEND/frp/frpc.toml <<FRPC
serverAddr = "{addr}"
serverPort = 7000
auth.method = "token"
auth.token = "{token}"

[[proxies]]
name = "dbp-ctl"
type = "tcp"
localIP = "127.0.0.1"
localPort = {ctl}
remotePort = {ctl}

[[proxies]]
name = "dbp-panel"
type = "tcp"
localIP = "127.0.0.1"
localPort = {panel}
remotePort = {panel}
FRPC

# 生成 supervisord 配置
NODE=$(command -v node || echo "/usr/bin/node")
sed -e "s|__PEND__|$PEND|g" -e "s|__NODE__|$NODE|g" $PEND/conf/dbp.conf.tpl > $PEND/conf/dbp.conf

echo "[4/4] 拉起服务"
cd $PEND
PEND=$PEND CTL_PORT={ctl} PANEL_PORT={panel} sh bin/ensure.sh 2>&1 | tail -20

echo "===== 部署完成 ====="
"""

# 外层：让豆包执行的指令
outer = "请帮我在沙箱执行这个部署脚本，全部完成后把最后 25 行输出发我：\n\n"
outer += "F=/tmp/dbp-install.sh\n"
outer += "cat > $F <<'INSTALL_END'\n"
outer += inner
outer += "INSTALL_END\n\n"
outer += "bash $F 2>&1 | tail -25\n"

print(outer)
PYEOF

echo
echo "================================================"
echo "  部署完成！"
echo "================================================"
echo
echo "【中转机信息】"
echo "  frps 地址:  $FRPS_ADDR:7000"
echo "  frp token:  $FRPS_TOKEN"
echo "  访问入口:   http://$FRPS_ADDR/"
echo "  1Panel:     http://$FRPS_ADDR/panel/"
echo
echo "【下一步】"
echo "  1. 打开豆包，新建会话，切换到【云电脑】模式"
echo "  2. 把 /root/SANDBOX_CMDS.txt 里的内容发给它"
echo "  3. 等它执行完，访问上面的地址"
echo
echo "  完整指令已保存到: /root/SANDBOX_CMDS.txt"
echo
if [ -f /root/.dbp_installed ]; then
  warn "检测到这是重复部署，原有配置已保留"
else
  touch /root/.dbp_installed
fi
echo
