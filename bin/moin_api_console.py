#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
moin_api_console.py — 18800 纯接口管理台（无扫码、无浏览器 UI）
全部走已验证接口：ck_live2.txt + doubao_send.py + /im/chain/*
"""
import json, os, time, subprocess, urllib.request, urllib.parse, logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 18800
CK = "/root/ck_live2.txt"
TARGET = "38453425674259202"
UA = "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("console")

def ck_header():
    return "; ".join(l.strip() for l in open(CK) if "=" in l)

def db_post(path, body, ctype="application/json; encoding=utf-8"):
    url = "https://www.doubao.com/" + path + "?aid=497858&samantha_web=1"
    req = urllib.request.Request(url, data=json.dumps(body, separators=(",", ":")).encode(),
        headers={"Cookie": ck_header(), "Content-Type": ctype, "agw-js-conv": "str",
                 "User-Agent": UA, "Referer": "https://www.doubao.com/chat/"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())

def recent():
    b = {"cmd":3200,"uplink_body":{"pull_recent_conv_chain_uplink_body":{"conv_version":0,"limit":20,"message_count_per_conv":1,"option":{"not_need_message":False,"need_complete_conversation":True,"need_coco_conversation":True,"need_coco_bot":True,"pc_pin_query_type":0},"api_version":1,"direction":3}},"sequence_id":"c1","channel":2,"version":"1"}
    return db_post("im/chain/recent_conv", b)

def single(cid, limit=8):
    b = {"cmd":3100,"uplink_body":{"pull_singe_chain_uplink_body":{"conversation_id":cid,"anchor_index":9007199254740991,"conversation_type":3,"direction":1,"limit":limit,"ext":{},"filter":{"index_list":[]},"evaluate_ab_params":"","evaluate_common_params":"","option":{"lazy_load_strategy":0}}},"sequence_id":"c2","channel":2,"version":"1"}
    return db_post("im/chain/single", b)

def alive():
    try:
        d = recent()
        cells = d.get("downlink_body",{}).get("pull_recent_conv_chain_downlink_body",{}).get("cells",[])
        return {"ok": True, "sessions": len(cells)}
    except Exception as e:
        return {"ok": False, "err": str(e)[:120]}

def send(text):
    r = subprocess.run(["python3", "/root/doubao_send.py", TARGET, text], capture_output=True, text=True, timeout=100)
    return r.stdout.strip()[:300]

HTML = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Moin 控制台 · 纯接口</title>
<style>
body{margin:0;background:#0d1117;color:#e6edf3;font:14px/1.6 -apple-system,system-ui,sans-serif}
header{padding:18px 24px;border-bottom:1px solid #30363d;display:flex;justify-content:space-between;align-items:center}
h1{margin:0;font-size:18px} .badge{background:#238636;color:#fff;padding:2px 10px;border-radius:12px;font-size:12px}
main{max-width:820px;margin:0 auto;padding:24px}
.card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:18px;margin-bottom:16px}
.card h2{margin:0 0 12px;font-size:15px;color:#79c0ff}
.row{display:flex;gap:10px;margin:8px 0;align-items:center}
input{flex:1;background:#0d1117;border:1px solid #30363d;color:#e6edf3;padding:9px 12px;border-radius:6px}
button{background:#238636;border:0;color:#fff;padding:9px 16px;border-radius:6px;cursor:pointer}
button.sec{background:#21262d;border:1px solid #30363d}
pre{background:#0d1117;padding:12px;border-radius:6px;overflow:auto;max-height:260px;font-size:12px;color:#8b949e}
.msg{border-left:3px solid #58a6ff;padding:4px 10px;margin:6px 0;font-size:13px}
.me{border-color:#3fb950;color:#7ee787}
.st{font-size:13px} .ok{color:#3fb950} .bad{color:#f85149}
</style></head><body>
<header><h1>Moin 控制台 <span class="badge">纯接口 · 无扫码</span></h1><span id="st" class="st">检测中…</span></header>
<main>
<div class="card"><h2>Cookie / 登录态</h2><div id="alive">…</div>
<div class="row"><button class="sec" onclick="refresh()">刷新状态</button></div></div>
<div class="card"><h2>发送消息 →「运行脚本恢复服务」</h2>
<div class="row"><input id="txt" placeholder="输入消息…" value="保活测试"><button onclick="doSend()">发送</button></div>
<pre id="sendOut">—</pre></div>
<div class="card"><h2>会话列表</h2><div id="sessions">…</div></div>
<div class="card"><h2>消息记录（验收标准）</h2><div class="row"><button class="sec" onclick="loadMsgs()">拉取最新</button></div><div id="msgs">…</div></div>
</main>
<script>
async function api(p){const r=await fetch(p);return r.json()}
async function refresh(){const d=await api('/api/alive');document.getElementById('alive').innerHTML=d.ok?'<span class="ok">● 登录有效 · '+d.sessions+' 个会话</span>':'<span class="bad">● '+d.err+'</span>';document.getElementById('st').innerHTML=d.ok?'<span class="ok">在线</span>':'<span class="bad">离线</span>'}
async function loadSessions(){const d=await api('/api/sessions');let h='';for(const c of d){h+='<div class="msg me">'+(c.name||c.id)+'</div>'}document.getElementById('sessions').innerHTML=h||'无'}
async function loadMsgs(){const d=await api('/api/messages');let h='';for(const m of d){h+='<div class="msg '+(m.me?'me':'')+'">'+m.text+'</div>'}document.getElementById('msgs').innerHTML=h||'无'}
async function doSend(){const t=document.getElementById('txt').value;const r=await fetch('/api/send?text='+encodeURIComponent(t));document.getElementById('sendOut').innerText=await r.text();setTimeout(loadMsgs,3000)}
refresh();loadSessions();loadMsgs();
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _json(self, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(200); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path == "/":
            b = HTML.encode(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        elif p.path == "/api/alive":
            self._json(alive())
        elif p.path == "/api/sessions":
            try:
                cells = recent().get("downlink_body",{}).get("pull_recent_conv_chain_downlink_body",{}).get("cells",[])
                self._json([{"id": c.get("conversation",{}).get("conversation_id",""), "name": c.get("conversation",{}).get("name","")} for c in cells])
            except Exception as e: self._json([{"id":"ERR","name":str(e)[:80]}])
        elif p.path == "/api/messages":
            try:
                msgs = single(TARGET).get("downlink_body",{}).get("pull_singe_chain_downlink_body",{}).get("messages",[])
                self._json([{"me": m.get("sender_id")=="2328113677082323", "text": (m.get("tts_content") or "")[:120]} for m in msgs])
            except Exception as e: self._json([{"me":False,"text":"ERR "+str(e)[:80]}])
        elif p.path == "/api/send":
            q = urllib.parse.parse_qs(p.query); self._json({"result": send(q.get("text",[""])[0])})
        else:
            self.send_response(404); self.end_headers()

if __name__ == "__main__":
    log.info("纯接口管理台启动 :%d", PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
