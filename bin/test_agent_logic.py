#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_agent_logic.py — agent 站点功能逻辑测试（无需沙箱在线）
用临时目录 mock PEND，验证所有站点操作的逻辑正确性。
运行: python3 test_agent_logic.py
"""
import os, re, json, tempfile, shutil, subprocess

PEND = tempfile.mkdtemp()
os.makedirs(os.path.join(PEND, "conf", "sites"), exist_ok=True)
os.makedirs(os.path.join(PEND, "www"), exist_ok=True)
os.makedirs(os.path.join(PEND, "ssl"), exist_ok=True)

def sh(cmd, t=30):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=t)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return 1, str(e)

def site_create(name):
    n = re.sub(r"[^A-Za-z0-9_-]", "", name)[:40]
    if not n: return {"ok": False, "error": "bad name"}
    root = os.path.join(PEND, "www", n); os.makedirs(root, exist_ok=True)
    idx = os.path.join(root, "index.html")
    if not os.path.exists(idx): open(idx, "w").write("<h1>" + n + "</h1>")
    conf = os.path.join(PEND, "conf", "sites", n + ".conf")
    open(conf, "w").write("server {\n  listen 127.0.0.1:8080;\n  server_name " + n + ".local;\n  root " + root + ";\n  location / { try_files $uri $uri/ =404; }\n}\n")
    return {"ok": True, "name": n, "root": root}

def site_add_domain(name, domain):
    n = re.sub(r"[^A-Za-z0-9_-]", "", name)[:40]
    d = re.sub(r"[^A-Za-z0-9._-]", "", domain)[:80]
    if not n or not d: return {"ok": False, "error": "参数无效"}
    path = os.path.join(PEND, "conf", "sites", n + ".conf")
    if not os.path.exists(path): return {"ok": False, "error": "站点不存在"}
    txt = open(path).read()
    m = re.search(r"server_name\s+([^;]+);", txt)
    if m:
        cur = m.group(1).strip()
        if d in cur.split(): return {"ok": True, "msg": "已存在"}
        txt = txt.replace(m.group(0), "server_name " + cur + " " + d + ";")
    else:
        txt = txt.replace("server {", "server {\n  server_name " + d + ";")
    open(path, "w").write(txt)
    return {"ok": True, "domains": d}

def site_ssl(name, enable=True):
    n = re.sub(r"[^A-Za-z0-9_-]", "", name)[:40]
    path = os.path.join(PEND, "conf", "sites", n + ".conf")
    if not os.path.exists(path): return {"ok": False, "error": "站点不存在"}
    crt, key = os.path.join(PEND,"ssl",n+".crt"), os.path.join(PEND,"ssl",n+".key")
    if enable and not os.path.exists(crt):
        rc, out = sh("openssl req -x509 -nodes -days 3650 -newkey rsa:2048 -keyout " + key + " -out " + crt + " -subj \"/CN=" + n + "\" 2>&1", 30)
        if rc != 0: return {"ok": False, "error": "证书失败: " + out[:100]}
    txt = open(path).read()
    if enable and "ssl_certificate" not in txt:
        txt = txt.replace("listen 127.0.0.1:8080;", "listen 127.0.0.1:8443 ssl;\n  ssl_certificate " + crt + ";\n  ssl_certificate_key " + key + ";")
        open(path, "w").write(txt)
    return {"ok": True, "ssl": enable}

def site_proxy(name, target):
    n = re.sub(r"[^A-Za-z0-9_-]", "", name)[:40]
    t = re.sub(r"[^A-Za-z0-9.:/_-]", "", target)[:120]
    if not n or not t: return {"ok": False, "error": "参数无效"}
    path = os.path.join(PEND, "conf", "sites", n + ".conf")
    if not os.path.exists(path): return {"ok": False, "error": "站点不存在"}
    txt = open(path).read()
    if "proxy_pass" not in txt:
        txt = re.sub(r"location / \{[^}]*\}", "location / {\n    proxy_pass " + t + ";\n  }", txt)
        open(path, "w").write(txt)
    return {"ok": True, "proxy": t}

def site_delete(name):
    n = re.sub(r"[^A-Za-z0-9_-]", "", name)[:40]
    p = os.path.join(PEND, "conf", "sites", n + ".conf")
    if os.path.exists(p): os.remove(p)
    return {"ok": True, "deleted": n}

def site_list():
    out = []
    d = os.path.join(PEND, "conf", "sites")
    if not os.path.isdir(d): return out
    for f in sorted(os.listdir(d)):
        if not f.endswith(".conf"): continue
        txt = open(os.path.join(d, f), errors="ignore").read()
        doms = re.findall(r"server_name\s+([^;]+);", txt)
        out.append({"name": f[:-5],
            "domains": [x.strip() for x in (doms[0].split() if doms else [])],
            "ssl": "ssl_certificate" in txt, "proxy": "proxy_pass" in txt})
    return out

PASS = 0; FAIL = 0
def chk(name, cond, extra=""):
    global PASS, FAIL
    if cond: PASS += 1; print("  PASS  " + name + " " + str(extra))
    else: FAIL += 1; print("  FAIL  " + name + " " + str(extra))

print("=" * 50)
print(" agent 站点功能逻辑测试")
print("=" * 50)

print("\n[1] 新建站点")
r = site_create("blog")
chk("创建成功", r["ok"])
chk("目录存在", os.path.isdir(r["root"]))
chk("vhost生成", os.path.exists(os.path.join(PEND,"conf","sites","blog.conf")))

print("\n[2] 绑定域名")
r = site_add_domain("blog","blog.example.com")
chk("绑定成功", r["ok"])
txt = open(os.path.join(PEND,"conf","sites","blog.conf")).read()
chk("server_name含新域名", "blog.example.com" in txt)

print("\n[3] 绑定第二个域名")
site_add_domain("blog","www.example.com")
txt = open(os.path.join(PEND,"conf","sites","blog.conf")).read()
chk("多域名累加", "blog.example.com" in txt and "www.example.com" in txt)

print("\n[4] 重复绑定")
r = site_add_domain("blog","blog.example.com")
chk("识别已存在", r.get("msg")=="已存在")

print("\n[5] 开 SSL")
r = site_ssl("blog", True)
chk("SSL开启", r.get("ok"))
txt = open(os.path.join(PEND,"conf","sites","blog.conf")).read()
chk("配置含ssl_certificate", "ssl_certificate" in txt)
chk("监听8443", "8443" in txt)

print("\n[6] 反向代理")
r = site_proxy("blog","http://127.0.0.1:3000")
chk("反代成功", r.get("ok"))
txt = open(os.path.join(PEND,"conf","sites","blog.conf")).read()
chk("配置含proxy_pass", "proxy_pass" in txt)

print("\n[7] 站点列表")
lst = site_list()
chk("列表有1个", len(lst)==1, lst)
chk("域名正确", lst[0]["domains"][0]=="blog.local")
chk("SSL标记", lst[0]["ssl"]==True)
chk("反代标记", lst[0]["proxy"]==True)

print("\n[8] 非法参数")
chk("空域名拒绝", site_add_domain("blog","")["ok"]==False)
chk("不存在站点拒绝", site_add_domain("nosuch","x.com")["ok"]==False)
chk("空反代拒绝", site_proxy("blog","")["ok"]==False)

print("\n[9] 删除站点")
r = site_delete("blog")
chk("删除成功", r["ok"])
chk("配置文件已移除", not os.path.exists(os.path.join(PEND,"conf","sites","blog.conf")))
chk("列表已空", len(site_list())==0)

shutil.rmtree(PEND)
print("\n" + "=" * 50)
print(" 结果: %d 通过, %d 失败" % (PASS, FAIL))
print("=" * 50)
exit(0 if FAIL == 0 else 1)
