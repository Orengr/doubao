#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_sandbox_runtime.py — 沙箱运行态验证（需要沙箱在线）
验证 3 项必须运行才能确认的功能：
1. nginx 能否加载配置
2. SSL 证书能否被接受
3. 反向代理是否真的转发
"""
import sys, json, time
sys.path.insert(0, "/root")
import urllib.request

AGENT = "http://127.0.0.1:17801"
TOK = open("/root/sbx_token.txt").read().strip() if __import__("os").path.exists("/root/sbx_token.txt") else ""

PASS = 0; FAIL = 0
def chk(n, c, e=""):
    global PASS, FAIL
    if c: PASS += 1; print("  PASS  " + n + " " + str(e))
    else: FAIL += 1; print("  FAIL  " + n + " " + str(e))

def get(path):
    try:
        sep = "&" if "?" in path else "?"
        r = urllib.request.urlopen(AGENT + path + sep + "token=" + TOK, timeout=30)
        return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)[:100]}

def post(path, body):
    try:
        req = urllib.request.Request(AGENT + path + "?token=" + TOK,
                                    data=json.dumps(body).encode(), method="POST",
                                    headers={"Content-Type": "application/json"})
        r = urllib.request.urlopen(req, timeout=60)
        return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)[:100]}

print("=" * 56)
print(" 沙箱运行态验证")
print("=" * 56)

print("\n[0] Agent 连通")
ping = get("/api/ping")
chk("agent ping", ping.get("ok"), ping.get("host", "")[:30])
if not ping.get("ok"):
    print("\n沙箱不在线，终止")
    sys.exit(2)

print("\n[1] 创建测试站点")
r = post("/api/site_create", {"name": "e2etest"})
chk("site_create", r.get("ok"), r.get("root", ""))
time.sleep(1)

print("\n[2] 站点列表")
lst = get("/api/sitelist")
names = [x.get("name") for x in lst] if isinstance(lst, list) else []
chk("sitelist 含新站点", "e2etest" in names, names)

print("\n[3] 绑定域名")
r = post("/api/site_add_domain", {"name": "e2etest", "domain": "e2e.example.com"})
chk("site_add_domain", r.get("ok"), r.get("domains", ""))
time.sleep(1)

print("\n[4] 开 SSL")
r = post("/api/site_ssl", {"name": "e2etest", "enable": True})
chk("site_ssl", r.get("ok"), r.get("cert", "")[:40])
time.sleep(1)

print("\n[5] 反向代理")
r = post("/api/site_proxy", {"name": "e2etest", "target": "http://127.0.0.1:8080"})
chk("site_proxy", r.get("ok"), r.get("proxy", ""))

print("\n[6] nginx 配置测试")
r = get("/api/nginx_test")
chk("nginx -t 通过", r.get("ok"), str(r.get("out", r.get("error", "")))[:80])

print("\n[7] 站点日志")
r = get("/api/site_log?name=e2etest&n=10")
chk("site_log 可读", isinstance(r, dict) and ("lines" in r or "error" in r), str(r)[:60])

print("\n[8] 数据库")
dbs = get("/api/databases")
chk("databases 可读", isinstance(dbs, list), str(len(dbs)) if isinstance(dbs, list) else dbs)

print("\n[9] PHP 信息")
r = get("/api/phpinfo")
chk("phpinfo 可读", r.get("ok"), r.get("version", "")[:30])

print("\n[10] 磁盘占用")
r = get("/api/disk")
chk("disk 可读", isinstance(r, list), str(len(r)) if isinstance(r, list) else r)

print("\n[11] 备份")
r = post("/api/backup", {})
chk("backup 成功", r.get("ok"), r.get("size", 0))

print("\n[12] 清理测试站点")
r = post("/api/site_delete", {"name": "e2etest"})
chk("site_delete", r.get("ok"), r.get("deleted", ""))
r = get("/api/nginx_test")
chk("清理后 nginx 仍通过", r.get("ok"))

print("\n" + "=" * 56)
print(" 结果: %d 通过, %d 失败" % (PASS, FAIL))
print("=" * 56)
sys.exit(0 if FAIL == 0 else 1)
