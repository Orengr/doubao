#!/bin/bash
# install-1panel.sh — 从成品包安装 1Panel（数据目录指向持久卷）
#
# 成品包（doubao-bundle.tar.gz）解压后自带 1panel 二进制，
# 本脚本只负责：注册到系统路径 + 改 BASE_DIR 指向持久卷 + 设默认密码
set -e

PEND="${PEND:-/home/user/.dsh_pend}"
P1DIR="$PEND/1panel"
P1DATA="$PEND/1panel-data"
LOG="$PEND/log/install-1panel.log"
mkdir -p "$PEND/log" "$P1DATA"
exec > >(tee -a "$LOG") 2>&1

echo "===== $(date '+%F %T') 安装 1Panel ====="

SUDO=""
if sudo -n true 2>/dev/null; then SUDO="sudo"; fi

# 成品包二进制
if [ ! -x "$P1DIR/1panel" ]; then
  echo "错误: $P1DIR/1panel 不存在（成品包未解压或不含 1panel）"
  exit 1
fi

# 注册到系统路径
$SUDO cp "$P1DIR/1panel" /usr/local/bin/1panel
$SUDO cp "$P1DIR/1pctl" /usr/local/bin/1pctl
$SUDO chmod +x /usr/local/bin/1panel /usr/local/bin/1pctl

# 关键：BASE_DIR 指向持久卷（10T hpvs_fs）
$SUDO sed -i "s|^BASE_DIR=.*|BASE_DIR=${P1DATA}|" /usr/local/bin/1pctl
echo "BASE_DIR 已设为 $P1DATA"

# ---------- 设置默认登录信息（开箱即用）----------
DEFAULT_USER="${PANEL_USER:-admin}"
DEFAULT_PASS="${PANEL_PASS:-123456}"
if command -v 1pctl >/dev/null 2>&1; then
  printf "%s\n%s\n" "$DEFAULT_PASS" "$DEFAULT_PASS" | \
    (sudo -n 1pctl update password 2>/dev/null || 1pctl update password) >/dev/null 2>&1 || true
  echo "[*] 面板默认账号: $DEFAULT_USER / $DEFAULT_PASS"
  echo "[*] 修改密码: 1pctl update password"
fi

command -v 1pctl >/dev/null && 1pctl user-info 2>/dev/null | head -6 || true
echo "===== 安装完成 ====="
