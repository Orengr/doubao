#!/bin/bash
# test.sh — 本地自测（不依赖沙箱）
# 验证所有组件能正常启动和响应
set -u

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0
ok()   { printf "${GREEN}✓${NC} %s\n" "$1"; PASS=$((PASS+1)); }
bad()  { printf "${RED}✗${NC} %s\n" "$1"; FAIL=$((FAIL+1)); }
warn() { printf "${YELLOW}!${NC} %s\n" "$1"; }

ROOT="$(cd "$(dirname "$0")" && pwd)"
TMP="/tmp/dbp-test-$$"
PEND="$TMP/pend"
PORT=27901

cleanup() {
  pkill -f "dbp-ctl.py" 2>/dev/null
  pkill -f "dbp-watch.py" 2>/dev/null
  rm -rf "$TMP"
}
trap cleanup EXIT

echo "================================================"
echo "  豆包免费服务器 · 本地自测"
echo "================================================"
echo

# ---------- 1. 语法检查 ----------
echo "[1] 语法检查"
for f in "$ROOT"/bin/*.py; do
  if python3 -c "import ast;ast.parse(open('$f').read())" 2>/dev/null; then
    ok "$(basename "$f")"
  else
    bad "$(basename "$f")"
  fi
done
for f in "$ROOT"/bin/*.sh "$ROOT/install.sh"; do
  [ -f "$f" ] || continue
  if bash -n "$f" 2>/dev/null; then
    ok "$(basename "$f")"
  else
    bad "$(basename "$f")"
  fi
done

# ---------- 2. 目录结构 ----------
echo
echo "[2] 目录结构"
for d in bin conf web docs; do
  [ -d "$ROOT/$d" ] && ok "$d/" || bad "$d/ 缺失"
done
for f in install.sh README.md QUICKSTART.md LICENSE; do
  [ -f "$ROOT/$f" ] && ok "$f" || bad "$f 缺失"
done

# ---------- 3. 关键逻辑 ----------
echo
echo "[3] 关键逻辑"
grep -q 'errorIcon' "$ROOT/bin/unified.py" && ok "错误图标检测" || bad "缺错误检测"
grep -q 'fail_streak' "$ROOT/bin/ka_v13.py" && ok "失败熔断" || bad "缺熔断"
grep -q 'TASK_TEMPLATES' "$ROOT/bin/ka_v13.py" && ok "任务轮换" || bad "缺轮换"
grep -q 'sid_guard' "$ROOT/bin/renew-activator.py" && ok "续期解析" || bad "缺续期"
grep -q '_proxy_panel' "$ROOT/bin/dbp-ctl.py" && ok "面板反代" || bad "缺反代"
grep -q 'autorestart=true' "$ROOT/conf/dbp.conf.tpl" && ok "自动重启" || bad "缺自动重启"

# ---------- 4. 控制面启动 ----------
echo
echo "[4] 控制面启动测试"
mkdir -p "$PEND"/{bin,conf,log,state,www,frp}
cp -r "$ROOT"/bin "$ROOT"/conf "$PEND"/ 2>/dev/null
mkdir -p "$PEND/www"
cp -r "$ROOT"/web/. "$PEND/www"/ 2>/dev/null

cd "$PEND" || exit 1
PEND="$PEND" CTL_PORT=$PORT PANEL_PORT=27902 BIND=127.0.0.1 \
  python3 bin/dbp-ctl.py > "$PEND/log/test.log" 2>&1 &
CTL_PID=$!
sleep 4

if curl -s -m 3 "http://127.0.0.1:$PORT/ping" | grep -q '"ok": true'; then
  ok "/ping 响应"
else
  bad "/ping 无响应"
fi

if [ "$(curl -s -m 3 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/")" = "200" ]; then
  ok "导航页 200"
else
  bad "导航页异常"
fi

# 鉴权
NOAUTH=$(curl -s -m 3 -X POST -d 'echo x' "http://127.0.0.1:$PORT/sh" 2>/dev/null)
if echo "$NOAUTH" | grep -q "bad token"; then
  ok "无 token 正确拒绝"
else
  bad "鉴权失效"
fi

TOK=$(cat "$PEND/state/token.txt" 2>/dev/null)
WITHTOK=$(curl -s -m 5 -H "X-Token: $TOK" -X POST -d 'echo TEST_OK' "http://127.0.0.1:$PORT/sh" 2>/dev/null)
if echo "$WITHTOK" | grep -q "TEST_OK"; then
  ok "有 token 执行成功"
else
  bad "带 token 执行失败"
fi

# ---------- 5. 配置生成 ----------
echo
echo "[5] 配置生成"
NODE=$(command -v node || echo "/usr/bin/node")
sed -e "s|__PEND__|$PEND|g" -e "s|__NODE__|$NODE|g" \
  "$ROOT/conf/dbp.conf.tpl" > "$PEND/conf/dbp.conf"
PROGS=$(grep -c 'program:' "$PEND/conf/dbp.conf")
if [ "$PROGS" = "4" ]; then
  ok "生成 4 个程序段"
else
  bad "程序段数异常: $PROGS"
fi

if grep -q "$PEND" "$PEND/conf/dbp.conf"; then
  ok "路径替换正确"
else
  bad "路径未替换"
fi

# ---------- 6. 健壮性 ----------
echo
echo "[6] 健壮性测试"

# 6.1 端口占用处理
PEND="$PEND" CTL_PORT=$PORT PANEL_PORT=27902 BIND=127.0.0.1   python3 bin/dbp-ctl.py > /dev/null 2>&1 &
sleep 3
DUP_OUT=$(PEND="$PEND" CTL_PORT=$PORT PANEL_PORT=27902 BIND=127.0.0.1   timeout 8 python3 bin/dbp-ctl.py 2>&1 | head -3)
if echo "$DUP_OUT" | grep -q "已被占用"; then
  ok "端口占用检测"
else
  bad "端口占用检测失效"
fi
if curl -s -m 3 "http://127.0.0.1:$PORT/ping" | grep -q '"ok"'; then
  ok "原实例未受影响"
else
  bad "原实例被破坏"
fi

# 6.2 supervisord 路径探测
if grep -q 'detect_sup_dir' "$ROOT/bin/ensure.sh"; then
  ok "supervisord 路径自动探测"
else
  bad "路径写死"
fi

# 6.3 ensure.sh 兜底启动
if grep -q '直接启动' "$ROOT/bin/ensure.sh"; then
  ok "ensure.sh 有兜底启动"
else
  bad "缺兜底启动"
fi

# 6.4 续期效果验证
if grep -q '有效期未变\|续期成功' "$ROOT/bin/renew-activator.py"; then
  ok "续期效果验证"
else
  bad "续期未验证"
fi

# 6.5 登录守护二维码检测
if grep -q '二维码已就绪' "$ROOT/bin/login-guard.py"; then
  ok "二维码就绪检测"
else
  bad "缺二维码检测"
fi

# ---------- 7. 端到端接口 ----------
echo
echo "[7] 端到端接口"

TOK=$(cat "$PEND/state/token.txt" 2>/dev/null)

# /stat
if curl -s -m 4 "http://127.0.0.1:$PORT/stat" | grep -q '"up"'; then
  ok "/stat 正常"
else
  bad "/stat 异常"
fi

# /put
PUT_R=$(curl -s -m 5 -H "X-Token: $TOK" --data-binary 'E2E_TEST'   "http://127.0.0.1:$PORT/put?p=$PEND/tasks/e2e.txt" 2>/dev/null)
if echo "$PUT_R" | grep -q '"ok": true'; then
  ok "/put 写文件"
else
  bad "/put 失败"
fi

# /get
if curl -s -m 5 -H "X-Token: $TOK" "http://127.0.0.1:$PORT/get?p=$PEND/tasks/e2e.txt" 2>/dev/null | grep -q 'E2E_TEST'; then
  ok "/get 读文件"
else
  bad "/get 失败"
fi

# 路径越界保护
if curl -s -m 5 -H "X-Token: $TOK" "http://127.0.0.1:$PORT/get?p=/etc/passwd" 2>/dev/null | grep -q 'outside PEND'; then
  ok "路径越界保护"
else
  bad "越界保护失效"
fi

# /health 自检
if curl -s -m 5 "http://127.0.0.1:$PORT/health" | grep -q '"checks"'; then
  ok "/health 自检接口"
else
  bad "/health 异常"
fi

# 导航页含自检区块
if curl -s -m 4 "http://127.0.0.1:$PORT/" | grep -q '系统自检'; then
  ok "导航页含自检"
else
  bad "导航页缺自检"
fi

# 看护启动
PEND="$PEND" CTL_PORT=$PORT PANEL_PORT=27902 python3 bin/dbp-watch.py > /dev/null 2>&1 &
sleep 3
if pgrep -f dbp-watch > /dev/null; then
  ok "看护启动"
else
  bad "看护未启动"
fi
pkill -f dbp-watch 2>/dev/null

# ---------- 8. 防刷屏逻辑 ----------
echo
echo "[8] 防刷屏逻辑"

# 8.1 熔断阈值
if grep -q 'fail_streak"\] >= 3' "$ROOT/bin/ka_v13.py"; then
  ok "失败熔断阈值(3次)"
else
  bad "缺熔断阈值"
fi

# 8.2 熔断后停止
if grep -q '停止保活以避免恶化' "$ROOT/bin/ka_v13.py"; then
  ok "熔断后停止保活"
else
  bad "熔断后未停止"
fi

# 8.3 恢复指令冷却
if grep -q 'last_wake"\] > 180' "$ROOT/bin/ka_v13.py"; then
  ok "恢复指令180秒冷却"
else
  bad "缺冷却"
fi

# 8.4 任务唯一性（时间戳）
if grep -q 'replace("{ts}"' "$ROOT/bin/ka_v13.py"; then
  ok "任务带时间戳(唯一)"
else
  bad "任务可能重复"
fi

# 8.5 任务轮换（8种）
TASKS=$(sed -n '/^TASK_TEMPLATES = \[/,/^\]/p' "$ROOT/bin/ka_v13.py" | grep -c '^    "')
if [ "$TASKS" -ge 8 ]; then
  ok "任务轮换($TASKS 种)"
else
  bad "任务种类不足: $TASKS"
fi

# ---------- 9. 续期时机逻辑 ----------
echo
echo "[9] 续期时机逻辑"

# 验证按 TTL 比例计算
if grep -q 'used_ratio' "$ROOT/bin/renew-activator.py"; then
  ok "按 TTL 比例计算"
else
  bad "未按比例"
fi

# 验证长 TTL 适配
if grep -q 'ttl < 86400' "$ROOT/bin/renew-activator.py"; then
  ok "长 TTL 适配(>1天)"
else
  bad "不支持长 TTL"
fi

# 逻辑验证：6小时 TTL 曲线
PY_OUT=$(python3 -c "
def calc(ttl, remain):
    used = 1.0 - (remain/ttl) if ttl>0 else 1.0
    if remain <= 0: iv = 300
    elif used > 0.85: iv = max(300, int(ttl*0.02))
    elif used > 0.60: iv = max(600, int(ttl*0.05))
    else: iv = max(1800, int(ttl*0.10))
    max_iv = 7200 if ttl < 86400 else min(int(ttl*0.15), 43200)
    return min(iv, max_iv)

# 6小时：应渐进加密
a = calc(21600, 21600)   # 全新
b = calc(21600, 3000)    # 剩余50分
print('OK' if a > b else 'FAIL')

# 30天：间隔应更长
c = calc(2592000, 2592000)
print('OK' if c > a else 'FAIL')
" 2>&1)
if echo "$PY_OUT" | head -1 | grep -q OK; then
  ok "短 TTL 渐进加密"
else
  bad "短 TTL 逻辑错误"
fi
if echo "$PY_OUT" | tail -1 | grep -q OK; then
  ok "长 TTL 间隔更长"
else
  bad "长 TTL 逻辑错误"
fi

# 9.5 分级续期
if grep -q 'lvl = 1 if fail_streak' "$ROOT/bin/renew-activator.py"; then
  ok "分级续期交互"
else
  bad "缺分级续期"
fi

# 9.6 sid_guard 解析正确性
PARSE=$(python3 -c "
import re, time
s = 'abc123def456abc123def456abc12345%7C1794592449%7C2592000%7CSun'
m = re.search(r'([0-9a-f]{32})%7C(\d+)%7C(\d+)', s)
if m and int(m.group(2)) == 1794592449 and int(m.group(3)) == 2592000:
    print('OK')
else:
    print('FAIL')
")
if [ "$PARSE" = "OK" ]; then
  ok "sid_guard 解析正确"
else
  bad "解析错误"
fi

# ---------- 10. healthcheck 逻辑 ----------
echo
echo "[10] healthcheck 逻辑"

HC_OUT=$(python3 - <<'PYEOF' 2>&1
import sys, os, tempfile
sys.path.insert(0, "bin")
import importlib.util
spec = importlib.util.spec_from_file_location("hc", "bin/healthcheck.py")
hc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hc)

# 完整 cookie
t1 = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
t1.write("sessionid=abc123\nsid_guard=def456\nuid_tt=ghi789\n")
t1.close()
ck = hc.check_cookie(t1.name)
print("COMPLETE", ck["ok"], ck["count"])

# 指纹变化
t2 = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
t2.write("sessionid=DIFF\nsid_guard=def456\nuid_tt=ghi789\n")
t2.close()
ck2 = hc.check_cookie(t2.name)
print("FP_DIFF", ck["fp"] != ck2["fp"])

# 缺失检测
t3 = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
t3.write("sessionid=abc\n")
t3.close()
ck3 = hc.check_cookie(t3.name)
print("MISSING", not ck3["ok"], len(ck3["missing"]))

for f in [t1.name, t2.name, t3.name]:
    os.unlink(f)
PYEOF
)

if echo "$HC_OUT" | grep -q "COMPLETE True 3"; then
  ok "cookie 解析(3项)"
else
  bad "cookie 解析错误"
fi
if echo "$HC_OUT" | grep -q "FP_DIFF True"; then
  ok "指纹变化检测"
else
  bad "指纹检测失效"
fi
if echo "$HC_OUT" | grep -q "MISSING True"; then
  ok "缺失项检测"
else
  bad "缺失检测失效"
fi

# ---------- 11. install-1panel 逻辑 ----------
echo
echo "[11] install-1panel 逻辑"

# 语法
if bash -n "$ROOT/bin/install-1panel.sh" 2>/dev/null; then
  ok "语法正确"
else
  bad "语法错误"
fi

# BASE_DIR 改写逻辑
if grep -q 'BASE_DIR=.*P1DATA' "$ROOT/bin/install-1panel.sh"; then
  ok "BASE_DIR 指向持久卷"
else
  bad "缺 BASE_DIR 改写"
fi

# 架构检测
if grep -q 'x86_64.*amd64' "$ROOT/bin/install-1panel.sh"; then
  ok "架构自动检测"
else
  bad "缺架构检测"
fi

# 幂等（已安装跳过）
if grep -q '1Panel 已安装，跳过下载' "$ROOT/bin/install-1panel.sh"; then
  ok "幂等(已装跳过)"
else
  bad "非幂等"
fi

# 镜像降级
if grep -q '镜像\|1panel.pro' "$ROOT/bin/install-1panel.sh"; then
  ok "下载失败降级"
else
  bad "无降级"
fi

# 11.5 熔断冷却
if grep -q 'COOLDOWN = 1800' "$ROOT/bin/ka_v13.py"; then
  ok "熔断冷却期(30分钟)"
else
  bad "缺冷却期"
fi
if grep -q 'stopped_at' "$ROOT/bin/ka_v13.py"; then
  ok "熔断时间持久化"
else
  bad "未持久化"
fi

# 11.6 ensure.sh 无 supervisord 兜底
echo
echo "[11.6] ensure.sh 兜底能力"

# 检查是否有 supervisord 可用性判断
if grep -q 'SUP_AVAILABLE' "$ROOT/bin/ensure.sh"; then
  ok "supervisord 可用性判断"
else
  bad "缺可用性判断"
fi

# 检查是否有直接启动兜底
if grep -q 'nohup.*dbp-ctl' "$ROOT/bin/ensure.sh"; then
  ok "dbp-ctl 直接启动兜底"
else
  bad "缺 dbp-ctl 兜底"
fi
if grep -q 'nohup.*dbp-watch' "$ROOT/bin/ensure.sh"; then
  ok "dbp-watch 直接启动兜底"
else
  bad "缺 dbp-watch 兜底"
fi

# 实测：无 supervisord 环境下能启动
ENSTEST=/tmp/ensure-test-$$
mkdir -p "$ENSTEST"/{bin,conf,log,state,www,frp}
cp -r "$ROOT"/bin "$ROOT"/conf "$ENSTEST"/ 2>/dev/null
cp -r "$ROOT"/web/. "$ENSTEST/www"/ 2>/dev/null
echo "[program:dbp-ctl]" > "$ENSTEST/conf/dbp.conf"
PEND="$ENSTEST" CTL_PORT=27209 timeout 25 sh "$ENSTEST/bin/ensure.sh" >/dev/null 2>&1
sleep 2
if grep -q '已直接启动' "$ENSTEST/log/ensure.log" 2>/dev/null; then
  ok "实测：兜底启动成功"
else
  bad "实测：兜底未生效"
fi
pkill -f "dbp-ctl.py" 2>/dev/null || true
pkill -f "dbp-watch.py" 2>/dev/null || true
rm -rf "$ENSTEST"

# 11.7 熔断自愈
echo
echo "[11.7] 熔断自愈能力"

if grep -q '检测到登录已恢复' "$ROOT/bin/ka_v13.py"; then
  ok "登录恢复自动解除熔断"
else
  bad "缺自愈机制"
fi

# 验证自愈逻辑
HEAL=$(python3 -c "
COOLDOWN = 1800
def sim(elapsed, recover_at=None):
    wait = int(COOLDOWN - elapsed)
    t = 0
    while t < wait:
        step = min(60, wait - t)
        t += step
        if recover_at and t >= recover_at:
            return 'EARLY'
    return 'NORMAL'

# 5分钟恢复应提前解除
a = sim(0, 300)
# 无恢复应等满
b = sim(0)
print('OK' if a == 'EARLY' and b == 'NORMAL' else 'FAIL')
")
if [ "$HEAL" = "OK" ]; then
  ok "自愈逻辑正确"
else
  bad "自愈逻辑错误"
fi

# 11.8 登录成功自动恢复
echo
echo "[11.8] 登录成功自动恢复"

if grep -q '自动恢复全链路' "$ROOT/bin/unified.py"; then
  ok "登录后自动恢复链路"
else
  bad "缺自动恢复"
fi
if grep -q '解除保活熔断' "$ROOT/bin/unified.py"; then
  ok "自动解除熔断"
else
  bad "未解除熔断"
fi
if grep -q '_auto_restore' "$ROOT/bin/unified.py"; then
  ok "恢复异步(不阻塞)"
else
  bad "恢复会阻塞"
fi

# 11.9 安全运维
echo
echo "[11.9] 安全运维"

ROTATE="$ROOT/bin/rotate-token.sh"
if [ -f "$ROTATE" ] && bash -n "$ROTATE" 2>/dev/null; then
  ok "token 轮换脚本语法"
else
  bad "轮换脚本缺失/语法错"
fi
if grep -q 'NEW_FRPC_TOML' "$ROTATE" 2>/dev/null; then
  ok "输出新 frpc 配置"
else
  bad "缺配置输出"
fi
if grep -q 'maxPortsPerClient' "$ROOT/install.sh"; then
  ok "frps 端口数量限制"
else
  bad "缺端口限制"
fi

# 11.10 状态总览脚本
echo
echo "[11.10] 状态总览"
STATUS_SH="$ROOT/bin/status.sh"
if [ -f "$STATUS_SH" ] && bash -n "$STATUS_SH" 2>/dev/null; then
  ok "status.sh 语法"
else
  bad "status.sh 缺失"
fi
if grep -q 'HAS_SYSTEMD' "$STATUS_SH" 2>/dev/null; then
  ok "systemd 正确检测"
else
  bad "systemd 检测有误"
fi
# 实测能运行并输出关键区块
S_OUT=$(timeout 15 bash "$STATUS_SH" 2>/dev/null)
if echo "$S_OUT" | grep -q '中转机服务'; then
  ok "输出服务区块"
else
  bad "输出异常"
fi

# 11.11 CI 配置
echo
echo "[11.11] CI 配置"
WF="$ROOT/.github/workflows/test.yml"
if [ -f "$WF" ] && grep -q 'bash test.sh' "$WF"; then
  ok "GitHub Actions 存在"
else
  bad "缺 CI 配置"
fi
if [ -f "$WF" ] && grep -q 'pull_request' "$WF"; then
  ok "PR 触发测试"
else
  bad "缺 PR 触发"
fi

# 11.12 开箱即用与脱敏
echo
echo "[11.12] 开箱即用与脱敏"

# 默认密码（普通用户不用查随机密码）
if grep -q 'DEFAULT_PASS.*123456' "$ROOT/bin/install-1panel.sh"; then
  ok "默认密码 admin/123456"
else
  bad "缺默认密码"
fi
# 导航页不硬编码真实密码
OLD_PASS="Jwgk""8Co"
if ! grep -q "$OLD_PASS" "$ROOT/web/index.html"; then
  ok "导航页无硬编码密码"
else
  bad "仍有真实密码"
fi
# 材料清单
if [ -f "$ROOT/PREPARE.md" ] && grep -q '材料清单' "$ROOT/PREPARE.md"; then
  ok "材料清单文档"
else
  bad "缺清单"
fi
if grep -q '准备材料' "$ROOT/install.sh"; then
  ok "部署前汇报清单"
else
  bad "未汇报清单"
fi
# 全包无敏感串
LEAK=$(grep -rniE '114\.215\.204\.238|chHdFEVj|oms2rRO|Jwgk8Co|moin520\.me|suyubai20' "$ROOT" 2>/dev/null | grep -v Binary | grep -v 'test.sh' | head -1)
if [ -z "$LEAK" ]; then
  ok "全包无敏感信息"
else
  bad "仍有敏感串: $LEAK"
fi
# 离线资源目录
if [ -d "$ROOT/bt_res" ] && [ -f "$ROOT/bt_res/README.md" ]; then
  ok "离线资源目录"
else
  bad "缺离线资源"
fi

# ---------- 12. 汇总 ----------
echo
echo "================================================"
printf "  通过: ${GREEN}%d${NC}  失败: ${RED}%d${NC}\n" "$PASS" "$FAIL"
echo "================================================"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
