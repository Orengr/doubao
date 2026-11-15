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
    if os.path.exists(mysqldump):
        sh(mysqldump + " --socket=" + MYSQL_SOCK + " -u root --all-databases > " + sqlfile, 120)
    tarf = os.path.join(outdir, "data_" + ts + ".tar.gz")
    rc, out = sh("cd " + PEND + " && tar czf " + tarf + " www conf state 2>/dev/null", 180)
    size = os.path.getsize(tarf) if os.path.exists(tarf) else 0
    return {"ok": rc == 0, "file": tarf, "size": size, "mysql_dump": sqlfile if os.path.exists(sqlfile) else ""}

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

def sites():
    """站点：扫描 /www/wwwroot 或 PEND/www"""
    out = []
    for base in ["/www/wwwroot", os.path.join(PEND, "www")]:
        if os.path.isdir(base):
            for d in sorted(os.listdir(base)):
                p = os.path.join(base, d)
                if os.path.isdir(p):
                    out.append({"name": d, "path": p, "files": len(glob.glob(p + "/*"))})
    return out

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
            if p == "/api/sites": return self._s(200, sites())
            if p == "/api/databases": return self._s(200, db_list())
            if p == "/api/tables":
                return self._s(200, db_tables(q.get("db",[""])[0]))
            if p == "/api/dbquery":
                return self._s(200, mysql_q(q.get("q",[""])[0]))
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
