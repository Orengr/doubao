#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""moin_api_console.py v2 — 18800 纯接口管理台
短信登录 / 登录历史 / 保活会话选择 / 发送 / 消息记录 / 云电脑模式 / 日志
"""
import json, os, time, subprocess, urllib.request, urllib.parse, logging, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, "/root")
import accounts_db as DB
import login_api as LOGIN
import keepctl as KEEP

PORT = 18800
UA = "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"
ACTIVE_F = "/root/active_account.json"
LOG_F = "/root/moin_api_console.log"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.FileHandler(LOG_F, encoding="utf-8"), logging.StreamHandler()])
log = logging.getLogger("console2")

def active():
    try: return json.load(open(ACTIVE_F))
    except Exception: return {}

def ck_file():
    a = active()
    if a.get("cookie_file") and os.path.exists(a["cookie_file"]): return a["cookie_file"]
    return "/root/ck_live2.txt"

def ck_header():
    return "; ".join(l.strip() for l in open(ck_file()) if "=" in l)

def db_post(path, body):
    url = "https://www.doubao.com/" + path + "?aid=497858&samantha_web=1"
    req = urllib.request.Request(url, data=json.dumps(body, separators=(",", ":")).encode(),
        headers={"Cookie": ck_header(), "Content-Type": "application/json; encoding=utf-8",
                 "agw-js-conv": "str", "User-Agent": UA, "Referer": "https://www.doubao.com/chat/"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())

def recent(limit=30):
    b = {"cmd":3200,"uplink_body":{"pull_recent_conv_chain_uplink_body":{"conv_version":0,"limit":limit,"message_count_per_conv":1,"option":{"not_need_message":False,"need_complete_conversation":True,"need_coco_conversation":True,"need_coco_bot":True,"pc_pin_query_type":0},"api_version":1,"direction":3}},"sequence_id":"web1","channel":2,"version":"1"}
    return db_post("im/chain/recent_conv", b)

def single(cid, limit=15):
    b = {"cmd":3100,"uplink_body":{"pull_singe_chain_uplink_body":{"conversation_id":cid,"anchor_index":9007199254740991,"conversation_type":3,"direction":1,"limit":limit,"ext":{},"filter":{"index_list":[]},"evaluate_ab_params":"","evaluate_common_params":"","option":{"lazy_load_strategy":0}}},"sequence_id":"web2","channel":2,"version":"1"}
    return db_post("im/chain/single", b)

def sessions():
    try:
        cells = recent().get("downlink_body",{}).get("pull_recent_conv_chain_downlink_body",{}).get("cells",[])
        return [{"id":c.get("conversation",{}).get("conversation_id",""),"name":c.get("conversation",{}).get("name","") or "(未命名)"} for c in cells]
    except Exception as e:
        return [{"id":"ERR","name":str(e)[:80]}]

def alive():
    s = sessions()
    return {"ok": not (s and s[0]["id"]=="ERR"), "count": len(s), "err": s[0]["name"] if s and s[0]["id"]=="ERR" else ""}

def do_send(cid, text):
    r = subprocess.run(["python3","/root/doubao_send.py",cid,text], capture_output=True, text=True, timeout=110)
    return r.stdout.strip()[:400]

def cloud_mode():
    out = subprocess.run(["python3","/root/cloudmode.py"], capture_output=True, text=True, timeout=30).stdout.strip()
    try: return json.loads(out)
    except Exception: return {"value":"?","label":"读取失败"}

HTML = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Moin 控制台 · 纯接口</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#0d1117;color:#e6edf3;font:14px/1.6 -apple-system,system-ui,sans-serif}
header{padding:16px 22px;border-bottom:1px solid #30363d;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
h1{margin:0;font-size:18px}.badge{background:#238636;color:#fff;padding:2px 10px;border-radius:12px;font-size:12px;margin-left:8px}
main{max-width:960px;margin:0 auto;padding:20px}
.card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px;margin-bottom:14px}
.card h2{margin:0 0 10px;font-size:15px;color:#79c0ff}
.row{display:flex;gap:8px;margin:8px 0;flex-wrap:wrap;align-items:center}
input,select{background:#0d1117;border:1px solid #30363d;color:#e6edf3;padding:8px 10px;border-radius:6px;flex:1;min-width:120px}
button{background:#238636;border:0;color:#fff;padding:8px 14px;border-radius:6px;cursor:pointer}
button.sec{background:#21262d;border:1px solid #30363d}button.warn{background:#9e6a03}
pre{background:#0d1117;padding:10px;border-radius:6px;overflow:auto;max-height:220px;font-size:12px;color:#8b949e;white-space:pre-wrap}
.msg{border-left:3px solid #58a6ff;padding:3px 10px;margin:5px 0;font-size:13px;white-space:pre-wrap;word-break:break-all}
.me{border-color:#3fb950;color:#7ee787}.ok{color:#3fb950}.bad{color:#f85149}.dim{color:#8b949e}
.tag{background:#21262d;border:1px solid #30363d;padding:2px 8px;border-radius:10px;font-size:12px}
.modal{position:fixed;inset:0;background:#0009;display:none;align-items:center;justify-content:center;z-index:9}
.modal .box{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:22px;max-width:460px;width:90%}
.hist{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px dashed #30363d;font-size:13px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:700px){.grid{grid-template-columns:1fr}}
</style></head><body>
<header><h1>Moin 控制台 <span class="badge">纯接口 · 无扫码</span></h1>
<span id="head" class="dim">初始化…</span></header>
<main>
<div class="card"><h2>① 登录（手机号 + 短信验证码，纯接口）</h2>
<div class="row"><input id="phone" placeholder="手机号" value="18053220144"><button onclick="loginSend()">获取验证码</button></div>
<div class="row"><input id="code" placeholder="6 位验证码"><button onclick="loginVerify()">提交登录</button></div>
<pre id="loginOut">—</pre></div>

<div class="card"><h2>② 当前账号 / 保活配置</h2>
<div id="acct">…</div>
<div class="row"><select id="keepSel"></select><button onclick="setKeep()">设为保活会话</button>
<button class="warn" onclick="activate()">启用保活</button><button class="sec" onclick="stopKeep()">停止保活</button></div>
<div class="row"><span class="tag" id="cloudMode">云电脑模式读取中…</span><button class="sec" onclick="setMode(9)">切到云电脑</button><button class="sec" onclick="setMode(0)">切到对话</button></div></div>

<div class="card"><h2>③ 发送消息</h2>
<div class="dim" id="sendTarget">—</div>
<div class="row"><select id="sendSel"></select></div>
<div class="row"><input id="txt" placeholder="输入消息…"><button onclick="doSend()">发送</button></div>
<pre id="sendOut">—</pre></div>

<div class="grid">
<div class="card"><h2>④ 会话列表</h2><div id="sessions">…</div></div>
<div class="card"><h2>⑤ 消息记录（验收标准）</h2>
<div class="row"><button class="sec" onclick="loadMsgs()">刷新</button></div><div id="msgs">…</div></div>
</div>

<div class="card"><h2>⑥ 历史登录</h2><div id="history">…</div></div>
<div class="card"><h2>⑦ 运行日志</h2><pre id="logbox">…</pre>
<div class="row"><button class="sec" onclick="loadLog()">刷新日志</button></div></div>
</main>

<div class="modal" id="modal"><div class="box">
<h2 style="margin-top:0">首次登录 · 配置保活会话</h2>
<p>这个账号第一次登录。选择一个会话用于自动保活；<b>不选也可以</b>，不选则保活保持关闭。</p>
<select id="modalSel"></select>
<div class="row" style="margin-top:14px"><button onclick="modalSave()">保存并启用保活</button>
<button class="sec" onclick="modalSkip()">跳过（不开启保活）</button></div>
</div></div>

<script>
let S={sessions:[],active:{},history:[]};
async function api(p){const r=await fetch(p);return r.json()}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
async function refreshAll(){
  const st=await api('/api/status'); S.active=st;
  const ss=await api('/api/sessions'); S.sessions=ss;
  const h=await api('/api/history'); S.history=h;
  const cm=await api('/api/cloud_mode');
  document.getElementById('cloudMode').innerText='当前模式: '+cm.label+'（value='+cm.value+'，9=云电脑）';
  const a=st.account;
  document.getElementById('head').innerHTML = a
    ? '<span class="ok">● 已登录 '+esc(a.name||a.uid)+'</span> · 保活 '+(st.service==='active'?'<span class="ok">运行中</span>':'<span class="bad">停止</span>')
    : '<span class="bad">● 未登录</span>';
  document.getElementById('acct').innerHTML = a
    ? '<div>UID: <b>'+esc(a.uid)+'</b> · 手机号: '+esc(a.phone||'—')+'</div>'+
      '<div>保活会话: '+(a.keep_conv_id?'<span class="ok">'+esc(a.keep_conv_name||a.keep_conv_id)+'</span>':'<span class="bad">未配置（保活关闭）</span>')+'</div>'+
      '<div class="dim">凭证: '+esc(a.cookie_file||'—')+' · 最近登录: '+new Date(a.last_login_at*1000).toLocaleString()+'</div>'
    : '<span class="bad">尚未登录任何账号</span>';
  const opts=S.sessions.map(s=>'<option value="'+esc(s.id)+'">'+esc(s.name)+' · '+esc(s.id)+'</option>').join('');
  document.getElementById('keepSel').innerHTML=opts;
  document.getElementById('sendSel').innerHTML=opts;
  document.getElementById('modalSel').innerHTML='<option value="">（不选择，保活关闭）</option>'+opts;
  if(a&&a.keep_conv_id){document.getElementById('keepSel').value=a.keep_conv_id;document.getElementById('sendSel').value=a.keep_conv_id}
  document.getElementById('sendTarget').innerText = a&&a.keep_conv_id
    ? '发送目标：账号 '+(a.name||a.uid)+' → 会话 '+esc(a.keep_conv_name||a.keep_conv_id)+'（可在下方下拉改选其它会话）'
    : '发送目标：请在上方下拉选择会话（当前未配置保活会话）';
  document.getElementById('sessions').innerHTML=S.sessions.map(s=>'<div class="msg me">'+esc(s.name)+'<br><span class="dim">'+esc(s.id)+'</span></div>').join('')||'无';
  document.getElementById('history').innerHTML=S.history.map(x=>'<div class="hist"><span>'+esc(x.name||x.uid)+' · '+esc(x.phone||'')+'</span><span class="dim">'+new Date(x.at*1000).toLocaleString()+' · '+esc(x.result)+'</span></div>').join('')||'无记录';
  loadMsgs();
}
async function loginSend(){
  const p=document.getElementById('phone').value;
  const r=await fetch('/api/login/send?phone='+encodeURIComponent(p));
  document.getElementById('loginOut').innerText=await r.text();
}
async function loginVerify(){
  const p=document.getElementById('phone').value,c=document.getElementById('code').value;
  const r=await fetch('/api/login/verify?phone='+encodeURIComponent(p)+'&code='+encodeURIComponent(c));
  const t=await r.text(); document.getElementById('loginOut').innerText=t;
  let d={};try{d=JSON.parse(t)}catch(e){}
  if(d.ok){ if(d.first_login){document.getElementById('modal').style.display='flex'} else {await refreshAll()} }
}
async function modalSave(){
  const cid=document.getElementById('modalSel').value;
  const d=JSON.parse(document.getElementById('loginOut').innerText);
  if(cid){await api('/api/keep/set?uid='+encodeURIComponent(d.uid)+'&cid='+encodeURIComponent(cid)+'&name='+encodeURIComponent((S.sessions.find(s=>s.id===cid)||{}).name||''))}
  document.getElementById('modal').style.display='none';
  await api('/api/keep/activate?uid='+encodeURIComponent(d.uid)); refreshAll();
}
async function modalSkip(){
  document.getElementById('modal').style.display='none';
  const d=JSON.parse(document.getElementById('loginOut').innerText);
  await api('/api/keep/activate?uid='+encodeURIComponent(d.uid)); refreshAll();
}
async function setKeep(){
  const d=S.active; if(!d.account){alert('未登录');return}
  const sel=document.getElementById('keepSel');
  await api('/api/keep/set?uid='+encodeURIComponent(d.account.uid)+'&cid='+encodeURIComponent(sel.value)+'&name='+encodeURIComponent(sel.options[sel.selectedIndex].text.split(' · ')[0]));
  refreshAll();
}
async function activate(){const d=S.active;if(!d.account){alert('未登录');return}await api('/api/keep/activate?uid='+encodeURIComponent(d.account.uid));refreshAll()}
async function stopKeep(){await api('/api/keep/stop');refreshAll()}
async function doSend(){
  const cid=document.getElementById('sendSel').value,t=document.getElementById('txt').value;
  if(!cid){alert('先选会话');return}
  const r=await fetch('/api/send?cid='+encodeURIComponent(cid)+'&text='+encodeURIComponent(t));
  document.getElementById('sendOut').innerText=await r.text();setTimeout(loadMsgs,3000);
}
async function loadMsgs(){
  const cid=document.getElementById('sendSel').value;if(!cid)return;
  const d=await api('/api/messages?cid='+encodeURIComponent(cid));
  document.getElementById('msgs').innerHTML=d.map(m=>'<div class="msg '+(m.me?'me':'')+'">'+esc(m.text)+'</div>').join('')||'无';
}
async function setMode(v){await api('/api/cloud_mode/set?v='+v);refreshAll()}
async function loadLog(){const r=await fetch('/api/log');document.getElementById('logbox').innerText=await r.text()}
refreshAll();loadLog();setInterval(refreshAll,15000);
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, obj, raw=False):
        b = (obj if raw else json.dumps(obj, ensure_ascii=False)).encode() if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8" if raw else "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        p = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(p.query)
        g = lambda k, d="": (q.get(k, [d])[0])
        try:
            if p.path == "/":
                b = HTML.encode(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
            elif p.path == "/api/status": self._send(KEEP.status())
            elif p.path == "/api/sessions": self._send(sessions())
            elif p.path == "/api/alive": self._send(alive())
            elif p.path == "/api/history": self._send(DB.history())
            elif p.path == "/api/cloud_mode": self._send(cloud_mode())
            elif p.path == "/api/cloud_mode/set":
                v = g("v", "9")
                out = subprocess.run(["python3","/root/cloudmode.py",v], capture_output=True, text=True, timeout=30).stdout.strip()
                self._send(out, raw=True)
            elif p.path == "/api/messages":
                cid = g("cid") or KEEP.status().get("keep_conv_id") or ""
                msgs = single(cid).get("downlink_body",{}).get("pull_singe_chain_downlink_body",{}).get("messages",[])
                self._send([{"me": m.get("sender_id")=="2328113677082323", "text": (m.get("tts_content") or "")[:150]} for m in msgs])
            elif p.path == "/api/send": self._send({"result": do_send(g("cid"), g("text"))})
            elif p.path == "/api/login/send":
                log.info("send_code phone=%s", g("phone")); self._send(LOGIN.send_code(g("phone")), raw=True)
            elif p.path == "/api/login/verify":
                phone, code = g("phone"), g("code")
                log.info("sms_login phone=%s", phone)
                out = subprocess.run(["python3","/root/login_api.py","verify",phone,code], capture_output=True, text=True, timeout=90).stdout.strip()
                try: d = json.loads(out)
                except Exception: self._send(out, raw=True); return
                if d.get("ok"):
                    acc = DB.get_account(d["uid"])
                    first = acc is None or not acc["keep_conv_id"]
                    DB.upsert_account(d["uid"], d["name"], phone, d["cookie_file"], json.dumps(d["device"]))
                    d["first_login"] = first
                    log.info("login ok uid=%s first=%s", d["uid"], first)
                self._send(d)
            elif p.path == "/api/keep/set": self._send(KEEP.set_keep(g("uid"), g("cid"), g("name")))
            elif p.path == "/api/keep/activate": self._send(KEEP.activate(g("uid")))
            elif p.path == "/api/keep/stop":
                subprocess.run(["systemctl","stop","ka-pure"], capture_output=True)
                self._send({"ok": True})
            elif p.path == "/api/log":
                try: txt = "".join(open(LOG_F).readlines()[-40:])
                except Exception: txt = "(no log)"
                self._send(txt, raw=True)
            else: self.send_response(404); self.end_headers()
        except Exception as e:
            log.exception("api error"); self._send({"error": str(e)[:200]})

if __name__ == "__main__":
    log.info("v2 管理台启动 :%d", PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
