#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sbx_agent.py — 沙箱侧面板 agent（纯标准库，无 Docker 依赖）
提供：系统概览/进程/文件管理/站点(nginx)/数据库/定时任务/容器化运行(proot)/日志/终端
监听 17999，token 鉴权。
"""
import os, sys, json, time, subprocess, shutil, glob, re, threading, signal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

PORT = int(os.environ.get("SBX_AGENT_PORT", "17802"))
PEND = os.environ.get("PEND", "/home/user/.dsh_pend")
TOKEN_FILE = os.path.join(PEND, "state", "token.txt")
START = time.time()

def token():
    try: return open(TOKEN_FILE).read().strip()
    except Exception: return ""

def sh(cmd, t=60, cwd=None):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=t, cwd=cwd)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired: return 124, "<timeout>"
    except Exception as e: return 1, str(e)

def safe(path):
    p = os.path.abspath(path)
    if not p.startswith(PEND) and not p.startswith("/home/user") and not p.startswith("/tmp"):
        return None
    return p


MYSQL = PEND + "/server/mysql/bin/mysql"
MYSQL_SOCK = PEND + "/state/mysql.sock"

def mysql_q(sql):
    cmd = MYSQL + " --socket=" + MYSQL_SOCK + " -u root -N -B -e " + json.dumps(sql)
    rc, out = sh(cmd, 20)
    if rc != 0: return {"ok": False, "error": out[:300]}
    rows = [ln.split("\t") for ln in out.strip().split("\n") if ln.strip()]
    return {"ok": True, "rows": rows}

def db_list():
    r = mysql_q("SHOW DATABASES")
    if not r.get("ok"): return []
    skip = {"information_schema","performance_schema","mysql","sys"}
    return [x[0] for x in r["rows"] if x and x[0] not in skip]

def db_tables(db):
    r = mysql_q("SHOW TABLES FROM `" + db.replace("`","") + "`")
    return [x[0] for x in r["rows"]] if r.get("ok") else []

def svc_status():
    items = []
    def alive(name, cmd, t=4):
        rc, _ = sh(cmd, t); items.append({"name": name, "ok": rc == 0})
    alive("控制面 17800", "curl -s -m 2 http://127.0.0.1:17800/ping | grep -q ok")
    alive("面板 Agent", "curl -s -m 2 http://127.0.0.1:17802/api/ping?token=" + token() + " | grep -q ok")
    alive("frpc 隧道", "pgrep -x frpc >/dev/null")
    alive("nginx", "pgrep -x nginx >/dev/null")
    alive("MySQL 8.0", "test -S " + MYSQL_SOCK + " && " + MYSQL + " --socket=" + MYSQL_SOCK + " -u root -e \"select 1\" >/dev/null 2>&1")
    alive("PHP 8.1", "test -x " + PEND + "/server/php/bin/php")
    return items


def site_create(name):
    n = re.sub(r"[^A-Za-z0-9_-]", "", name)[:40]
    if not n: return {"ok": False, "error": "bad name"}
    root = os.path.join(PEND, "www", n)
    os.makedirs(root, exist_ok=True)
    idx = os.path.join(root, "index.html")
    if not os.path.exists(idx):
        open(idx, "w", encoding="utf-8").write("<h1>" + n + " is running</h1>\n<p>Moin Panel · " + time.strftime("%Y-%m-%d %H:%M") + "</p>")
    # 写 nginx vhost（站点监控脚本会加载）
    vh = os.path.join(PEND, "conf", "sites")
    os.makedirs(vh, exist_ok=True)
    conf = os.path.join(vh, n + ".conf")
    open(conf, "w", encoding="utf-8").write(
        "server {\n  listen 127.0.0.1:8080;\n  server_name " + n + ".local;\n  root " + root + ";\n  index index.html;\n  location / { try_files $uri $uri/ =404; }\n}\n")
    return {"ok": True, "name": n, "root": root, "vhost": conf}

def cron_add(expr, cmd):
    rc, out = sh("crontab -l 2>/dev/null | grep -v '^#' | cat -; echo " + json.dumps(expr + " " + cmd), 10)
    try:
        cur = subprocess.run("crontab -l 2>/dev/null", shell=True, capture_output=True, text=True, timeout=10).stdout
        new = (cur.rstrip() + "\n" if cur.strip() else "") + expr + " " + cmd + "\n"
        p = subprocess.run("crontab -", shell=True, input=new, capture_output=True, text=True, timeout=10)
        return {"ok": p.returncode == 0, "line": expr + " " + cmd, "err": (p.stderr or "")[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}

def backup():
    ts = time.strftime("%Y%m%d_%H%M%S")
    outdir = os.path.join(PEND, "backup")
    os.makedirs(outdir, exist_ok=True)

    sqlfile = os.path.join(outdir, "mysql_" + ts + ".sql")
    mysqldump = PEND + "/server/mysql/bin/mysqldump"
    mysql_ok = False
    if os.path.exists(mysqldump) and os.path.exists(MYSQL_SOCK):
        rc, _ = sh(mysqldump + " --socket=" + MYSQL_SOCK + " -u root --all-databases > " + sqlfile, 120)
        mysql_ok = (rc == 0 and os.path.exists(sqlfile))

    dirs = [d for d in ("www", "conf", "state", "tasks") if os.path.isdir(os.path.join(PEND, d))]
    tarf = os.path.join(outdir, "data_" + ts + ".tar.gz")
    tar_ok = False
    if dirs:
        rc, out = sh("cd " + PEND + " && tar czf " + tarf + " " + " ".join(dirs) + " 2>&1", 180)
        tar_ok = (rc == 0 and os.path.exists(tarf))

    size = os.path.getsize(tarf) if os.path.exists(tarf) else 0
    return {
        "ok": tar_ok or mysql_ok,
        "file": tarf if tar_ok else "",
        "size": size,
        "mysql_dump": sqlfile if mysql_ok else "",
        "packed_dirs": dirs,
        "mysql_ok": mysql_ok,
        "tar_ok": tar_ok,
    }
def site_list():
    """完整站点信息：含域名、端口、SSL、状态"""
    out = []
    vh_dir = os.path.join(PEND, "conf", "sites")
    if not os.path.isdir(vh_dir): return out
    for f in sorted(os.listdir(vh_dir)):
        if not f.endswith(".conf"): continue
        path = os.path.join(vh_dir, f)
        try: txt = open(path, encoding="utf-8", errors="ignore").read()
        except Exception: continue
        name = f[:-5]
        domains = re.findall(r"server_name\s+([^;]+);", txt)
        ports = re.findall(r"listen\s+(\d+)", txt)
        rootm = re.search(r"root\s+([^;]+);", txt)
        ssl_on = "ssl_certificate" in txt
        proxy = "proxy_pass" in txt
        out.append({
            "name": name, "file": path,
            "domains": [d.strip() for d in (domains[0].split() if domains else [])],
            "ports": ports, "root": rootm.group(1) if rootm else "",
            "ssl": ssl_on, "proxy": proxy,
            "running": "listen" in txt
        })
    return out

def site_add_domain(name, domain):
    """给站点绑定域名"""
    n = re.sub(r"[^A-Za-z0-9_-]", "", name)[:40]
    d = re.sub(r"[^A-Za-z0-9._-]", "", domain)[:80]
    if not n or not d: return {"ok": False, "error": "参数无效"}
    path = os.path.join(PEND, "conf", "sites", n + ".conf")
    if not os.path.exists(path): return {"ok": False, "error": "站点不存在"}
    txt = open(path, encoding="utf-8").read()
    m = re.search(r"server_name\s+([^;]+);", txt)
    if m:
        cur = m.group(1).strip()
        if d in cur.split(): return {"ok": True, "msg": "已存在"}
        txt = txt.replace(m.group(0), "server_name " + cur + " " + d + ";")
    else:
        txt = txt.replace("server {", "server {\n  server_name " + d + ";")
    open(path, "w", encoding="utf-8").write(txt)
    return {"ok": True, "name": n, "domains": d, "need_reload": True}

def site_ssl(name, enable=True):
    """站点 SSL（自签证书，内网用）"""
    n = re.sub(r"[^A-Za-z0-9_-]", "", name)[:40]
    path = os.path.join(PEND, "conf", "sites", n + ".conf")
    if not os.path.exists(path): return {"ok": False, "error": "站点不存在"}
    ssl_dir = os.path.join(PEND, "ssl")
    os.makedirs(ssl_dir, exist_ok=True)
    crt, key = os.path.join(ssl_dir, n + ".crt"), os.path.join(ssl_dir, n + ".key")
    if enable and not os.path.exists(crt):
        rc, out = sh("openssl req -x509 -nodes -days 3650 -newkey rsa:2048 -keyout " + key + " -out " + crt +
                     " -subj \"/CN=" + n + "\" 2>&1", 30)
        if rc != 0: return {"ok": False, "error": "生成证书失败: " + out[:150]}
    txt = open(path, encoding="utf-8").read()
    if enable and "ssl_certificate" not in txt:
        txt = txt.replace("listen 127.0.0.1:8080;",
                          "listen 127.0.0.1:8443 ssl;\n  ssl_certificate " + crt + ";\n  ssl_certificate_key " + key + ";")
        open(path, "w", encoding="utf-8").write(txt)
    return {"ok": True, "name": n, "ssl": enable, "cert": crt if enable else ""}

def site_proxy(name, target):
    """反向代理：站点转发到指定后端"""
    n = re.sub(r"[^A-Za-z0-9_-]", "", name)[:40]
    t = re.sub(r"[^A-Za-z0-9.:/_-]", "", target)[:120]
    if not n or not t: return {"ok": False, "error": "参数无效"}
    path = os.path.join(PEND, "conf", "sites", n + ".conf")
    if not os.path.exists(path): return {"ok": False, "error": "站点不存在"}
    txt = open(path, encoding="utf-8").read()
    if "proxy_pass" not in txt:
        txt = re.sub(r"location / \{[^}]*\}",
                     "location / {\n    proxy_pass " + t + ";\n    proxy_set_header Host $host;\n    proxy_set_header X-Real-IP $remote_addr;\n  }", txt)
        open(path, "w", encoding="utf-8").write(txt)
    return {"ok": True, "name": n, "proxy": t}

def site_delete(name):
    n = re.sub(r"[^A-Za-z0-9_-]", "", name)[:40]
    if not n: return {"ok": False, "error": "参数无效"}
    vh = os.path.join(PEND, "conf", "sites", n + ".conf")
    if os.path.exists(vh): os.remove(vh)
    return {"ok": True, "deleted": n}

def nginx_reload():
    rc, out = sh("sudo -n nginx -t 2>&1 | tail -2", 15)
    if rc != 0: return {"ok": False, "error": out[:200]}
    rc2, out2 = sh("sudo -n nginx -s reload 2>&1", 15)
    return {"ok": rc2 == 0, "out": (out + out2)[:300]}


def site_log(name, lines=50):
    n = re.sub(r"[^A-Za-z0-9_-]", "", name)[:40]
    for cand in [PEND+"/log/nginx_"+n+".log", PEND+"/log/site_"+n+".log", "/www/wwwlogs/"+n+".log"]:
        if os.path.exists(cand):
            try:
                ls = open(cand, errors="ignore").readlines()[-lines:]
                return {"ok": True, "file": cand, "lines": "".join(ls)}
            except Exception as e:
                return {"ok": False, "error": str(e)[:100]}
    return {"ok": False, "error": "无日志文件"}

def php_info():
    php = PEND + "/server/php/bin/php"
    if not os.path.exists(php): return {"ok": False, "error": "PHP 未安装"}
    rc, out = sh(php + " -v 2>&1 | head -2", 10)
    rc2, mods = sh(php + " -m 2>&1 | head -20", 10)
    return {"ok": True, "version": out.strip(), "modules": mods.strip().split(chr(10))[:15]}

def disk_usage():
    rc, out = sh("du -sh " + PEND + "/* 2>/dev/null | sort -rh | head -12", 30)
    return [l.split(chr(9)) for l in out.strip().split(chr(10)) if chr(9) in l]

def overview():
    rc, up = sh("cat /proc/uptime")
    up_s = float(up.split()[0]) if rc == 0 and up.split() else 0
    rc, mem = sh("free -m | sed -n 2p")
    m = mem.split() if rc == 0 else []
    rc, dsk = sh("df -h " + PEND + " | tail -1")
    d = dsk.split() if rc == 0 else []
    rc, cpu = sh("nproc")
    rc, load = sh("cat /proc/loadavg")
    rc, host = sh("uname -n")
    rc, kern = sh("uname -r")
    rc, osr = sh("cat /etc/os-release 2>/dev/null | head -2 | tr '\n' ' '")
    procs = 0
    try: procs = len(os.listdir("/proc")) - 2
    except Exception: pass
    return {
        "host": host.strip(), "uptime_sec": int(up_s), "kernel": kern.strip(), "os": osr.strip()[:80],
        "cpu_cores": int(cpu.strip()) if cpu.strip().isdigit() else 0,
        "load": load.strip(), "procs": procs,
        "mem_total_mb": int(m[1]) if len(m) > 1 else 0, "mem_used_mb": int(m[2]) if len(m) > 2 else 0,
        "mem_free_mb": int(m[3]) if len(m) > 3 else 0,
        "disk_total": d[1] if len(d) > 1 else "", "disk_used": d[2] if len(d) > 2 else "",
        "disk_avail": d[3] if len(d) > 3 else "", "disk_pct": d[4] if len(d) > 4 else "",
        "agent_uptime": int(time.time() - START),
    }

def processes():
    rc, out = sh("ps -eo pid,ppid,pcpu,pmem,rss,comm,args --sort=-pcpu --no-headers | head -40")
    rows = []
    for line in out.strip().split("\n"):
        p = line.split(None, 6)
        if len(p) >= 6:
            rows.append({"pid": p[0], "ppid": p[1], "cpu": p[2], "mem": p[3], "rss_mb": int(p[4])//1024 if p[4].isdigit() else 0, "name": p[5], "cmd": (p[6] if len(p) > 6 else "")[:120]})
    return rows

def services():
    return svc_status()

def containers():
    """容器化运行（proot 隔离），列出运行中的"""
    rc, out = sh("ps -eo pid,args | grep -E 'proot|chroot' | grep -v grep | head -20")
    rows = []
    for line in out.strip().split("\n"):
        if line.strip():
            p = line.strip().split(None, 1)
            rows.append({"pid": p[0], "cmd": p[1][:150] if len(p) > 1 else ""})
    return rows

def cron_jobs():
    rc, out = sh("crontab -l 2>/dev/null; ls " + os.path.join(PEND, "cron") + " 2>/dev/null")
    return out.strip().split("\n") if out.strip() else []

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def _s(self, code, obj, ctype="application/json; charset=utf-8"):
        b = obj.encode() if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try: self.wfile.write(b)
        except Exception: pass
    def _ok(self, q):
        return q.get("token", [""])[0] == token()
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query); p = u.path
        if p == "/api/ping":
            if not self._ok(q): return self._s(401, {"error": "bad token"})
            return self._s(200, {"ok": True, "host": overview()["host"], "uptime": int(time.time()-START)})
        if not self._ok(q): return self._s(401, {"error": "bad token"})
        try:
            if p == "/api/sitelist": return self._s(200, site_list())
            if p == "/api/nginx_test": return self._s(200, nginx_reload())
            if p == "/api/sites": return self._s(200, sites())
            if p == "/api/databases": return self._s(200, db_list())
            if p == "/api/tables":
                return self._s(200, db_tables(q.get("db",[""])[0]))
            if p == "/api/dbquery":
                return self._s(200, mysql_q(q.get("q",[""])[0]))
            if p == "/api/phpinfo": return self._s(200, php_info())
            if p == "/api/disk": return self._s(200, disk_usage())
            if p == "/api/site_log":
                return self._s(200, site_log(q.get("name",[""])[0], int(q.get("n",["50"])[0])))
            if p == "/api/overview": return self._s(200, overview())
            if p == "/api/procs": return self._s(200, processes())
            if p == "/api/services": return self._s(200, services())
            if p == "/api/databases": return self._s(200, db_list())
            if p == "/api/tables":
                return self._s(200, db_tables(q.get("db",[""])[0]))
            if p == "/api/dbquery":
                return self._s(200, mysql_q(q.get("q",[""])[0]))
            if p == "/api/containers": return self._s(200, containers())
            if p == "/api/cron": return self._s(200, cron_jobs())
            if p == "/api/ls":
                d = safe(q.get("p", [PEND])[0]) or PEND
                if not os.path.isdir(d): return self._s(400, {"error": "not dir"})
                items = []
                for n in sorted(os.listdir(d)):
                    fp = os.path.join(d, n)
                    try: st = os.stat(fp)
                    except Exception: continue
                    items.append({"name": n, "dir": os.path.isdir(fp), "size": st.st_size, "mtime": int(st.st_mtime)})
                return self._s(200, {"path": d, "items": items})
            if p == "/api/read":
                f = safe(q.get("p", [""])[0])
                if not f or not os.path.isfile(f): return self._s(400, {"error": "bad file"})
                if os.path.getsize(f) > 2*1024*1024: return self._s(413, {"error": "too large"})
                return self._s(200, open(f, "r", errors="ignore").read(200000), "text/plain; charset=utf-8")
            if p == "/api/log":
                f = safe(q.get("p", [PEND + "/log/sbx_agent.log"])[0])
                n = int(q.get("n", ["200"])[0])
                if not f or not os.path.isfile(f): return self._s(400, {"error": "no log"})
                lines = open(f, "r", errors="ignore").readlines()[-n:]
                return self._s(200, "".join(lines), "text/plain; charset=utf-8")
            return self._s(404, {"error": "not found"})
        except Exception as e:
            return self._s(500, {"error": str(e)[:200]})
    def do_POST(self):
        u = urlparse(self.path); q = parse_qs(u.query); p = u.path
        if not self._ok(q): return self._s(401, {"error": "bad token"})
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n).decode("utf-8", "ignore") if n else ""
        try:
            if p == "/api/sh":
                d = json.loads(body) if body else {}
                rc, out = sh(d.get("cmd", ""), int(d.get("t", 60)), d.get("cwd"))
                return self._s(200, {"rc": rc, "out": out[-40000:]})
            if p == "/api/write":
                d = json.loads(body); f = safe(d.get("path", ""))
                if not f: return self._s(400, {"error": "bad path"})
                os.makedirs(os.path.dirname(f), exist_ok=True)
                open(f, "w", encoding="utf-8").write(d.get("content", ""))
                return self._s(200, {"ok": True, "path": f})
            if p == "/api/site_add_domain":
                d = json.loads(body) if body else {}
                return self._s(200, site_add_domain(d.get("name",""), d.get("domain","")))
            if p == "/api/site_ssl":
                d = json.loads(body) if body else {}
                return self._s(200, site_ssl(d.get("name",""), d.get("enable",True)))
            if p == "/api/site_proxy":
                d = json.loads(body) if body else {}
                return self._s(200, site_proxy(d.get("name",""), d.get("target","")))
            if p == "/api/site_delete":
                d = json.loads(body) if body else {}
                return self._s(200, site_delete(d.get("name","")))
            if p == "/api/nginx_reload":
                return self._s(200, nginx_reload())
            if p == "/api/site_create":
                d = json.loads(body) if body else {}
                return self._s(200, site_create(d.get("name","")))
            if p == "/api/cron_add":
                d = json.loads(body) if body else {}
                return self._s(200, cron_add(d.get("expr",""), d.get("cmd","")))
            if p == "/api/backup":
                return self._s(200, backup())
            if p == "/api/run_container":
                # 容器化效果：proot 隔离运行（无 root 权限需求）
                d = json.loads(body)
                name = re.sub(r"[^A-Za-z0-9_-]", "", d.get("name", "app"))[:32]
                rootfs = d.get("rootfs", "")
                cmd = d.get("cmd", "/bin/sh")
                log = os.path.join(PEND, "log", name + ".log")
                os.makedirs(os.path.dirname(log), exist_ok=True)
                if rootfs and os.path.isdir(rootfs):
                    full = "cd " + rootfs + " && nohup proot -r " + rootfs + " -b /proc -b /dev -b /sys -w / " + cmd + " >> " + log + " 2>&1 &"
                else:
                    full = "cd " + PEND + " && nohup " + cmd + " >> " + log + " 2>&1 &"
                rc, out = sh(full, 15)
                return self._s(200, {"ok": rc == 0, "log": log, "out": out[-2000:]})
            return self._s(404, {"error": "not found"})
        except Exception as e:
            return self._s(500, {"error": str(e)[:200]})

if __name__ == "__main__":
    os.makedirs(os.path.join(PEND, "log"), exist_ok=True)
    print("sbx_agent on", PORT, "PEND", PEND, flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
