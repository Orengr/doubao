#!/usr/bin/env python3
"""
dbp-ctl.py — 沙箱控制面（1Panel 代理 + 状态 + 命令执行）

设计要点：
  - 数据全部在 /home/user/.dsh_pend（10T 持久卷）
  - 由 supervisord 托管，被沙箱回收后自动恢复
  - /sh 与 /put 需 token；/ping /stat 公开
  - /panel/* 反代到本机 1Panel（默认 18090）
"""
import os, json, time, subprocess, secrets, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BIND = os.environ.get("BIND", "127.0.0.1")
PORT = int(os.environ.get("CTL_PORT", "17800"))
PEND = os.environ.get("PEND", "/home/user/.dsh_pend")
PANEL_PORT = int(os.environ.get("PANEL_PORT", "18090"))

STATE_DIR = os.path.join(PEND, "state")
LOG_DIR = os.path.join(PEND, "log")
os.makedirs(STATE_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

TOKFILE = os.path.join(STATE_DIR, "token.txt")
if os.path.exists(TOKFILE):
    TOKEN = open(TOKFILE).read().strip()
else:
    TOKEN = secrets.token_urlsafe(24)
    open(TOKFILE, "w").write(TOKEN)
    os.chmod(TOKFILE, 0o600)

START = time.time()
open(os.path.join(STATE_DIR, "control.pid"), "w").write(str(os.getpid()))


def sh(cmd, timeout=90):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "<timeout>"
    except Exception as e:
        return 1, str(e)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _auth(self, q):
        return (self.headers.get("X-Token") or q.get("token", [""])[0]) == TOKEN

    # ---------- 1Panel 反向代理 ----------
    def _proxy_panel(self, method):
        try:
            path = self.path
            if path.startswith("/panel/"):
                path = path[6:]
            elif path == "/panel":
                path = "/"
            n = int(self.headers.get("Content-Length", 0))
            data = self.rfile.read(n) if n else None
            req = urllib.request.Request(
                f"http://127.0.0.1:{PANEL_PORT}{path}", data=data, method=method)
            for h in ("Content-Type", "Authorization", "Cookie", "Accept", "Accept-Language"):
                if self.headers.get(h):
                    req.add_header(h, self.headers.get(h))
            r = urllib.request.urlopen(req, timeout=90)
            body = r.read()
            self.send_response(r.status)
            for k, v in r.headers.items():
                if k.lower() in ("content-type", "content-length", "set-cookie", "transfer-encoding"):
                    continue
                self.send_header(k, v)
            self.send_header("Content-Type", r.headers.get("Content-Type", "application/octet-stream"))
            self.send_header("Content-Length", str(len(body)))
            sc = r.headers.get("Set-Cookie")
            if sc:
                self.send_header("Set-Cookie", sc)
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self._send(502, {"error": f"panel proxy failed: {str(e)[:100]}"})

    # ---------- GET ----------
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        p = u.path

        if p == "/panel" or p.startswith("/panel/"):
            return self._proxy_panel("GET")

        if p in ("/", "/index.html"):
            f = os.path.join(PEND, "www", "index.html")
            if os.path.exists(f):
                b = open(f, "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                try:
                    self.wfile.write(b)
                except Exception:
                    pass
                return
            return self._send(200, {"ok": True, "msg": "dbp-ctl running"})

        if p == "/ping":
            return self._send(200, {"ok": True, "uptime": int(time.time() - START),
                                    "host": os.uname().nodename})

        if p == "/stat":
            _, mem = sh("free -m | sed -n 2p", 10)
            _, disk = sh(f"df -h {PEND} | tail -1", 10)
            _, top = sh("ps -eo pid,pcpu,pmem,comm --sort=-pcpu --no-headers | head -6", 10)
            return self._send(200, {
                "up": int(time.time() - START),
                "host": os.uname().nodename,
                "mem": mem.strip(), "disk": disk.strip(),
                "top": top.strip().splitlines(), "pid": os.getpid()})

        if p == "/health":
            # 自检：逐项检查各组件状态
            checks = []

            # 1. 控制面自身
            checks.append({"name": "控制面", "ok": True,
                           "detail": f"uptime {int(time.time()-START)}s"})

            # 2. 1Panel
            panel_ok = False
            try:
                r = urllib.request.urlopen(f"http://127.0.0.1:{PANEL_PORT}/", timeout=5)
                panel_ok = r.status == 200
            except Exception:
                pass
            checks.append({"name": "1Panel", "ok": panel_ok,
                           "detail": f"port {PANEL_PORT}"})

            # 3. frpc 进程
            rc, out = sh("pgrep -x frpc | head -1", 5)
            frpc_ok = rc == 0 and out.strip().isdigit()
            checks.append({"name": "frpc", "ok": frpc_ok,
                           "detail": f"pid {out.strip()}" if frpc_ok else "未运行"})

            # 4. 持久卷
            _, dfout = sh(f"df -h {PEND} | tail -1", 5)
            checks.append({"name": "持久卷", "ok": bool(dfout.strip()),
                           "detail": dfout.strip()[:60]})

            # 5. 磁盘空间
            space_ok = True
            try:
                st = os.statvfs(PEND)
                free_gb = st.f_bavail * st.f_frsize / (1024**3)
                space_ok = free_gb > 0.5
                detail = f"剩余 {free_gb:.1f} GB"
            except Exception:
                detail = "无法读取"
            checks.append({"name": "磁盘空间", "ok": space_ok, "detail": detail})

            # 6. supervisord 配置
            sup_found = False
            for d in ["/opt/gem/supervisord", "/etc/supervisord.d",
                      "/etc/supervisor/conf.d"]:
                if os.path.exists(os.path.join(d, "dbp.conf")):
                    sup_found = True
                    break
            checks.append({"name": "supervisord", "ok": sup_found,
                           "detail": "已托管" if sup_found else "未托管"})

            all_ok = all(c["ok"] for c in checks)
            return self._send(200, {"ok": all_ok, "checks": checks,
                                    "host": os.uname().nodename,
                                    "uptime": int(time.time() - START)})

        if p == "/api/panelinfo":
            # 从 1pctl 读面板登录信息（不硬编码，只在本地使用）
            try:
                rc, out = sh("1pctl user-info 2>/dev/null", 15)
                user, pwd, entry = "", "", ""
                for ln in out.splitlines():
                    if "面板用户" in ln:
                        user = ln.split(":", 1)[-1].strip() if ":" in ln else ln.split()[-1]
                    elif "面板密码" in ln or "密码" in ln:
                        pwd = ln.split(":", 1)[-1].strip() if ":" in ln else ln.split()[-1]
                    elif "面板地址" in ln or "http" in ln:
                        entry = ln.strip()
                return self._send(200, {"ok": bool(user or pwd),
                                        "user": user, "password": pwd,
                                        "entry": entry})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:60]})

        if p == "/api/panelurl":
            return self._send(200, {"url": "/panel/", "port": PANEL_PORT})

        if not self._auth(q):
            return self._send(401, {"error": "bad token"})

        if p == "/get":
            fp = q.get("p", [""])[0]
            try:
                if not os.path.abspath(fp).startswith(PEND):
                    return self._send(403, {"error": "path outside PEND"})
                if os.path.getsize(fp) > 4 * 1024 * 1024:
                    return self._send(413, {"error": "file too large"})
                return self._send(200, open(fp, "rb").read(), "application/octet-stream")
            except Exception as e:
                return self._send(500, {"error": str(e)[:80]})

        return self._send(404, {"error": "not found"})

    # ---------- POST ----------
    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        p = u.path

        if p == "/panel" or p.startswith("/panel/"):
            return self._proxy_panel("POST")

        if not self._auth(q):
            return self._send(401, {"error": "bad token"})

        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n).decode("utf-8", "ignore") if n else ""

        if p == "/sh":
            rc, out = sh(body, int(q.get("t", ["90"])[0]))
            return self._send(200, {"rc": rc, "out": out[-60000:]})

        if p == "/put":
            fp = q.get("p", [""])[0]
            try:
                os.makedirs(os.path.dirname(fp), exist_ok=True)
                open(fp, "w", encoding="utf-8").write(body)
                return self._send(200, {"ok": True, "path": fp, "size": len(body)})
            except Exception as e:
                return self._send(500, {"error": str(e)[:80]})

        return self._send(404, {"error": "not found"})


def port_in_use(port, host="127.0.0.1"):
    import socket as _s
    try:
        c = _s.create_connection((host, port), timeout=1)
        c.close()
        return True
    except Exception:
        return False


def main():
    # 端口占用检测：优先判断是否是自己的旧实例
    if port_in_use(PORT):
        print(f"[dbp-ctl] 端口 {PORT} 已被占用", flush=True)
        # 检查现有实例是否健康
        try:
            import urllib.request as _u
            r = _u.urlopen(f"http://127.0.0.1:{PORT}/ping", timeout=4)
            if b'"ok"' in r.read():
                print(f"[dbp-ctl] 已有实例在运行且健康，本进程退出", flush=True)
                return 0
        except Exception:
            pass
        # 占用者不健康，等待其退出
        for i in range(10):
            time.sleep(2)
            if not port_in_use(PORT):
                break
        else:
            print(f"[dbp-ctl] 端口持续被占用，放弃启动", flush=True)
            return 1

    # 允许端口复用
    import socketserver as _ss
    _ss.TCPServer.allow_reuse_address = True

    try:
        srv = ThreadingHTTPServer((BIND, PORT), Handler)
    except OSError as e:
        print(f"[dbp-ctl] 绑定失败: {e}", flush=True)
        return 1

    print(f"[dbp-ctl] {BIND}:{PORT} panel={PANEL_PORT} token={TOKEN[:8]}...", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(main() or 0)
