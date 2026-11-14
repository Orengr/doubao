#!/bin/bash
# install-1panel.sh — 把 1Panel 装进沙箱持久卷
# 特点：数据目录在 /home/user/.dsh_pend/1panel-data（10T 持久卷）
set -e

PEND="${PEND:-/home/user/.dsh_pend}"
P1DIR="$PEND/1panel"
P1DATA="$PEND/1panel-data"
LOG="$PEND/log/install-1panel.log"
VERSION="${ONEPANEL_VERSION:-v1.10.34-lts}"
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64)  A=amd64 ;;
  aarch64) A=arm64 ;;
  *) echo "不支持的架构: $ARCH"; exit 1 ;;
esac

mkdir -p "$PEND/log" "$P1DIR" "$P1DATA"
exec > >(tee -a "$LOG") 2>&1

echo "===== $(date '+%F %T') 安装 1Panel $VERSION ($A) ====="

# 已安装则跳过
if command -v 1pctl >/dev/null 2>&1 && [ -x /usr/local/bin/1panel ]; then
  echo "1Panel 已安装，跳过下载"
else
  URL="https://resource.fit2cloud.com/1panel/package/stable/${VERSION}/release/1panel-${VERSION}-linux-${A}.tar.gz"
  # 优先从项目 GitHub 仓库的 bt_res 拉（用户 clone 后自带，零额外下载）
  GITHUB_RAW="${GITHUB_RAW:-https://raw.githubusercontent.com/Orengr/doubao/main}"
  cd /tmp
  echo "下载: $GITHUB_RAW/bt_res/1panel.tar.gz"
  curl -fsSL --max-time 180 -o 1p.tar.gz "$GITHUB_RAW/bt_res/1panel.tar.gz" || {
    echo "仓库离线包不可用，回退官方源"
    curl -fsSL -o 1p.tar.gz "$URL" || {
      echo "官方源失败，尝试镜像"
      curl -fsSL -o 1p.tar.gz "${URL/resource.fit2cloud.com/resource.1panel.pro}" || exit 1
    }
  }
  tar xzf 1p.tar.gz
  SRC="1panel-${VERSION}-linux-${A}"
  [ -d "$SRC" ] || SRC=$(ls -d 1panel-* 2>/dev/null | head -1)
  echo "解压目录: $SRC"

  cp -r "$SRC"/* "$P1DIR"/
  chmod +x "$P1DIR/1panel" "$P1DIR/1pctl" "$P1DIR/install.sh" 2>/dev/null || true

  # 注册 1pctl（需要 root）
  if [ -w /usr/local/bin ] || sudo -n true 2>/dev/null; then
    sudo cp "$P1DIR/1panel" /usr/local/bin/1panel 2>/dev/null || cp "$P1DIR/1panel" /usr/local/bin/1panel
    sudo cp "$P1DIR/1pctl" /usr/local/bin/1pctl 2>/dev/null || cp "$P1DIR/1pctl" /usr/local/bin/1pctl
    sudo chmod +x /usr/local/bin/1panel /usr/local/bin/1pctl 2>/dev/null || true
    # 关键：把 BASE_DIR 指向持久卷
    sudo sed -i "s|^BASE_DIR=.*|BASE_DIR=${P1DATA}|" /usr/local/bin/1pctl 2>/dev/null || \
      sed -i "s|^BASE_DIR=.*|BASE_DIR=${P1DATA}|" /usr/local/bin/1pctl
    echo "BASE_DIR 已设为 $P1DATA"
  else
    echo "警告：无法写入 /usr/local/bin，1Panel 可能无法直接用 1pctl 管理"
  fi
fi

echo "===== 安装完成 ====="
echo "数据目录: $P1DATA"

# ---------- 设置默认登录信息（开箱即用）----------
# 普通用户不用自己去查随机密码，统一用 admin / 123456
# 密码可通过 1pctl update password 随时修改
DEFAULT_USER="${PANEL_USER:-admin}"
DEFAULT_PASS="${PANEL_PASS:-123456}"

if command -v 1pctl >/dev/null 2>&1; then
  # 1pctl update password 是交互式的，用管道喂入新密码
  # 多数版本流程：输入新密码 → 确认新密码
  printf "%s\n%s\n" "$DEFAULT_PASS" "$DEFAULT_PASS" |     $SUDO 1pctl update password >/dev/null 2>&1 || true
  echo "[*] 面板默认账号: $DEFAULT_USER / $DEFAULT_PASS"
  echo "[*] 修改密码: 1pctl update password"
fi

command -v 1pctl >/dev/null && 1pctl user-info 2>/dev/null | head -6 || true
