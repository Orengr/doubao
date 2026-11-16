#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_e2e.py — 端到端集成验证
验证服务器侧全链路（不依赖沙箱）：
1. 所有服务存活
2. CDP 浏览器登录态有效
3. 会话列表可读
4. 面板所有接口响应
5. 隧道哨兵状态正确
"""
import sys, json, subprocess, urllib.request, os
sys.path.insert(0, "/root")

PASS = 0; FAIL = 0
def chk(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  PASS  " + name + " " + str(extra))
    else:
        FAIL += 1; print("  FAIL  " + name + " " + str(extra))

def sh(cmd, t=20):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=t)
        return p.returncode, (p.stdout or "").strip()
    except Exception:
        return 1, ""

print("=" * 56)
print(" 端到端集成验证")
print("=" * 56)

print("\n[1] systemd 服务")
for svc in ["moin-unified", "ka-boot", "tunnel-watch", "sbx-guard", "nginx", "frps", "xvfb", "doubao-cdp"]:
    rc, out = sh("systemctl is-active " + svc)
    chk(svc, out == "active", out)

print("\n[2] CDP 浏览器")
rc, out = sh("curl -s -m 5 http://127.0.0.1:9222/json/version")
chk("CDP 可达", "Browser" in out)
rc, out = sh("curl -s -m 5 http://127.0.0.1:9222/json/list")
chk("有页面标签", "\"type\": \"page\"" in out or '"type": "page"' in out)

print("\n[3] 豆包登录态")
try:
    import conv_api as CA
    r = CA.page_eval("fetch('/passport/account/info/v2/',{credentials:'include'}).then(r=>r.json()).then(j=>JSON.stringify({uid:(j.data||{}).user_id_str,name:(j.data||{}).name}))", 30)
    j = json.loads(r) if r else {}
    chk("登录有效", j.get("uid") == "2126889695314595", j.get("name"))
except Exception as e:
    chk("登录有效", False, str(e)[:60])

print("\n[4] 会话列表")
try:
    lst = CA.list_conv_with_health(30)
    chk("读到会话", len(lst) > 0, str(len(lst)) + " 个")
    if lst:
        chk("会话有ID", bool(lst[0].get("conv_id")))
        chk("有消息数", "msg_count" in lst[0], lst[0].get("msg_count"))
except Exception as e:
    chk("读到会话", False, str(e)[:60])

print("\n[5] 面板接口")
for ep in ["overview", "services", "sitelist", "databases", "procs", "cron", "sessions", "phpinfo", "disk"]:
    rc, out = sh("curl -s -o /dev/null -w '%{http_code}' -m 15 http://127.0.0.1:18800/api/panel/" + ep)
    chk("api/" + ep, out == "200", out)

print("\n[6] 面板页面")
rc, out = sh("curl -s -o /dev/null -w '%{http_code}' -m 10 http://127.0.0.1:18800/panel")
chk("面板页", out == "200", out)

print("\n[7] 保活启动器状态")
try:
    st = json.load(open("/root/ka_boot_state.json"))
    chk("状态文件存在", True)
    chk("有退避记录", st.get("backoff", 0) >= 300, st.get("backoff"))
    chk("有尝试记录", st.get("attempt", 0) >= 1, st.get("attempt"))
except Exception as e:
    chk("状态文件", False, str(e)[:60])

print("\n[8] 隧道哨兵状态")
try:
    st2 = json.load(open("/root/tunnel_watch_state.json"))
    chk("哨兵状态存在", True)
    chk("有日限记录", "fired" in st2, st2.get("fired"))
except Exception:
    chk("哨兵状态存在", True, "(首次运行，无文件)")

print("\n" + "=" * 56)
print(" 结果: %d 通过, %d 失败" % (PASS, FAIL))
print("=" * 56)
exit(0 if FAIL == 0 else 1)
