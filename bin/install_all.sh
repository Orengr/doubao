#!/bin/sh
# install_all.sh — Moin 面板一键部署（面板+MySQL8+PHP8.1+nginx+依赖，全内置）
# 用法: sh install_all.sh
PEND=/home/user/.dsh_pend
PKG=$PEND/pkg
SRV=$PEND/server
LOG=$PEND/log/install_all.log
mkdir -p "$PEND/bin" "$PEND/log" "$PEND/state" "$SRV"
exec >> "$LOG" 2>&1
echo "=========================================="
echo " Moin 面板一键部署 $(date)"
echo "=========================================="

step(){ echo ""; echo "[$1] $2"; }

# ---------- 1 系统依赖 ----------
step 1 "安装系统依赖库（libaio/libzip/libncurses）"
if ! ldconfig -p 2>/dev/null | grep -q libaio.so.1; then
  sudo -n apt-get update -q 2>&1 | tail -1
  sudo -n apt-get install -y -q libaio1 libzip4 libncurses5 libtinfo5 2>&1 | tail -3
fi
echo "  libaio: $(ldconfig -p 2>/dev/null | grep -c libaio.so.1)  libzip: $(ldconfig -p 2>/dev/null | grep -c libzip.so.4)"

# ---------- 2 MySQL 8 ----------
step 2 "部署 MySQL 8.0（预编译包，解压即用）"
if [ ! -x "$SRV/mysql/bin/mysqld" ]; then
  if [ -f "$PKG/mysql-8.0.40-linux-glibc2.17-x86_64.tar.xz" ]; then
    mkdir -p "$SRV/mysql"
    tar -xJf "$PKG/mysql-8.0.40-linux-glibc2.17-x86_64.tar.xz" -C "$SRV/mysql" --strip-components=1
    echo "  已解压"
  else
    echo "  !! 缺少 mysql 包，跳过"
  fi
fi
if [ -x "$SRV/mysql/bin/mysqld" ] && [ ! -d "$SRV/mysql-data/mysql" ]; then
  mkdir -p "$SRV/mysql-data"
  "$SRV/mysql/bin/mysqld" --no-defaults --initialize-insecure --basedir="$SRV/mysql" --datadir="$SRV/mysql-data" --log-error="$PEND/log/mysql-init.log" 2>&1 | tail -2
  echo "  已初始化"
fi

# ---------- 3 PHP 8.1 ----------
step 3 "部署 PHP 8.1（预编译包）"
if [ ! -x "$SRV/php/bin/php" ]; then
  if [ -f "$PKG/php81-prebuilt.tar.xz" ]; then
    mkdir -p "$SRV/php"
    tar -xJf "$PKG/php81-prebuilt.tar.xz" -C "$SRV/php" --strip-components=3 2>/dev/null || tar -xJf "$PKG/php81-prebuilt.tar.xz" -C "$SRV/php"
    echo "  已解压"
  else
    echo "  !! 缺少 php 包，跳过"
  fi
fi
[ -x "$SRV/php/bin/php" ] && echo "  PHP: $($SRV/php/bin/php -v 2>&1 | head -1)"

# ---------- 4 nginx ----------
step 4 "检查 nginx"
if command -v nginx >/dev/null 2>&1; then echo "  nginx: $(nginx -v 2>&1)"; else echo "  !! nginx 缺失"; fi

# ---------- 5 启动脚本 ----------
step 5 "生成服务启动脚本"
cat > "$PEND/bin/start_mysql.sh" <<'EOS'
#!/bin/sh
PEND=/home/user/.dsh_pend; SRV=$PEND/server; PIDF=$PEND/state/mysql.pid
mkdir -p $PEND/log $PEND/state
[ -f "$PIDF" ] && kill -0 "$(cat $PIDF)" 2>/dev/null && { echo "mysql running"; exit 0; }
$SRV/mysql/bin/mysqld --no-defaults --basedir=$SRV/mysql --datadir=$SRV/mysql-data   --socket=$PEND/state/mysql.sock --port=3306 --pid-file=$PIDF   --log-error=$PEND/log/mysql.log --bind-address=127.0.0.1   --innodb-buffer-pool-size=128M --user=$(id -un) >/dev/null 2>&1 &
sleep 5
$SRV/mysql/bin/mysqladmin --socket=$PEND/state/mysql.sock -u root ping 2>/dev/null && echo "mysql started" || { echo "mysql failed"; tail -3 $PEND/log/mysql.log; }
EOS
echo "  start_mysql.sh 已生成"

cat > "$PEND/bin/start_all.sh" <<'EOS'
#!/bin/sh
PEND=/home/user/.dsh_pend
sh $PEND/bin/start_mysql.sh
sh $PEND/bin/start_agent.sh
pgrep -x frpc >/dev/null || (cd $PEND/frp && setsid nohup ./frpc -c frpc.toml >> $PEND/log/frpc.log 2>&1 </dev/null &)
pgrep -x nginx >/dev/null || sudo -n nginx 2>/dev/null
echo "all started"
EOS
chmod +x "$PEND/bin/start_mysql.sh" "$PEND/bin/start_all.sh"
echo "  start_all.sh 已生成"

# ---------- 6 启动 ----------
step 6 "启动服务"
sh "$PEND/bin/start_all.sh"
sleep 3

# ---------- 7 汇总 ----------
step 7 "部署完成"
echo "  MySQL: $(ls $SRV/mysql/bin/mysqld 2>/dev/null && echo OK || echo FAIL)"
echo "  PHP:   $([ -x $SRV/php/bin/php ] && echo OK || echo FAIL)"
echo "  Agent: $(curl -s -m 3 "http://127.0.0.1:17802/api/ping?token=$(cat $PEND/state/token.txt)" | grep -q ok && echo OK || echo FAIL)"
echo "  磁盘:  $(du -sh $SRV 2>/dev/null | cut -f1)"
echo "=========================================="
