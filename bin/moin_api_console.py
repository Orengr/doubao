#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""moin_api_console.py v3 — 18800 纯接口管理台"""
import json, os, time, subprocess, urllib.request, urllib.parse, logging, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, "/root")
import accounts_db as DB
import login_api as LOGIN
import keepctl as KEEP
import conv_api as API
import chat_page as CHATP
import cloudmode as CM

PORT=18800; ACTIVE_F="/root/active_account.json"; LOG_F="/root/moin_api_console.log"
logging.basicConfig(level=logging.INFO,format="%(asctime)s %(message)s",
    handlers=[logging.FileHandler(LOG_F,encoding="utf-8"),logging.StreamHandler()])
log=logging.getLogger("console3")

def active():
    try: return json.load(open(ACTIVE_F))
    except Exception: return {}
def uid(): return active().get("uid","")

def sessions_with_status():
    uid_=uid(); out=API.sessions()
    acc=DB.get_account(uid_) if uid_ else None
    keep=acc["keep_conv_id"] if acc else ""
    for s in out:
        cv=DB.get_conv(uid_,s["id"])
        s["alive"]=cv["alive"]; s["dead_reason"]=cv["dead_reason"]
        s["keep"]=(s["id"]==keep)
        s["checked_at"]=cv["checked_at"]
    # 保活排第一
    out.sort(key=lambda x:(not x["keep"], x["name"]))
    return out

PANEL_TOKEN = "oms2rROVaDd8t8s9jWIYKBW1eYREoQbu"
PANEL_FALLBACK = "/cSK41ajJX5"

def panel_entrance():
    # 从沙箱持久卷读入口（控制面 /get 带 token）；失败回退缓存值
    try:
        url = "http://127.0.0.1:17800/get?token=" + PANEL_TOKEN + "&p=/home/user/.dsh_pend/state/panel_entrance.txt"
        r = urllib.request.urlopen(url, timeout=8)
        e = r.read().decode("utf-8","ignore").strip()
        if e.startswith("/") and len(e) < 40: return e
    except Exception: pass
    return PANEL_FALLBACK

def status():
    st=KEEP.status(); ss=sessions_with_status(); st["sessions"]=ss
    # 防假登录：会话列表读不出来（ERR/空）就视为未登录
    if ss and ss[0]["id"]=="ERR":
        st["account"]=None; st["logged_in"]=False
    else:
        st["logged_in"]=bool(st.get("account"))
    # 保活会话名以会话列表实时名字为准（避免账号库缓存旧名）
    if st.get("account") and st["account"].get("keep_conv_id"):
        k=st["account"]["keep_conv_id"]
        hit=next((x for x in ss if x["id"]==k), None)
        if hit: st["account"]["keep_conv_name"]=hit["name"]
    if uid(): st["settings"]=DB.all_settings(uid())
    st["panel_entrance"] = panel_entrance()
    return st

HTML = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Moin 控制台</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#0d1117;color:#e6edf3;font:14px/1.6 -apple-system,system-ui,sans-serif}
header{padding:14px 20px;border-bottom:1px solid #30363d;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;position:sticky;top:0;background:#0d1117;z-index:5}
h1{margin:0;font-size:17px}.badge{background:#238636;color:#fff;padding:2px 9px;border-radius:12px;font-size:11px;margin-left:6px}
main{max-width:1000px;margin:0 auto;padding:16px}
.card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px;margin-bottom:12px}
.card h2{margin:0 0 10px;font-size:15px;color:#79c0ff;display:flex;justify-content:space-between;align-items:center}
.row{display:flex;gap:8px;margin:8px 0;flex-wrap:wrap;align-items:center}
input,select{background:#0d1117;border:1px solid #30363d;color:#e6edf3;padding:7px 10px;border-radius:6px;flex:1;min-width:110px;font-size:13px}
button{background:#238636;border:0;color:#fff;padding:7px 13px;border-radius:6px;cursor:pointer;font-size:13px}
button.sec{background:#21262d;border:1px solid #30363d}button.warn{background:#9e6a03}button.sm{padding:4px 9px;font-size:12px}
pre{background:#0d1117;padding:10px;border-radius:6px;overflow:auto;max-height:180px;font-size:12px;color:#8b949e;white-space:pre-wrap}
.dim{color:#8b949e}.ok{color:#3fb950}.bad{color:#f85149}.green{color:#3fb950;font-weight:600}
.tag{background:#21262d;border:1px solid #30363d;padding:2px 8px;border-radius:10px;font-size:12px}
.conv{border:1px solid #30363d;border-radius:8px;padding:10px;margin:7px 0;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:8px}
.conv:hover{border-color:#58a6ff}.conv.keep{border:2px solid #238636;background:#12261a}
.conv.dead{opacity:.65;border-color:#f85149}
.conv .nm{font-weight:600}.conv .meta{font-size:11px;color:#8b949e}
.pill{font-size:11px;padding:1px 7px;border-radius:8px;white-space:nowrap}
.pill.live{background:#12341d;color:#3fb950}.pill.dead{background:#3a1418;color:#f85149}.pill.keep{background:#1b3a24;color:#7ee787}
.modal{position:fixed;inset:0;background:#000b;display:none;align-items:center;justify-content:center;z-index:9;padding:14px}
.modal .box{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:18px;max-width:760px;width:100%;max-height:90vh;overflow:auto}
.chat{background:#0d1117;border-radius:8px;padding:10px;max-height:46vh;overflow:auto;margin:10px 0}
.m{border-left:3px solid #58a6ff;padding:5px 10px;margin:6px 0;font-size:13px;white-space:pre-wrap;word-break:break-word}
.m.me{border-color:#3fb950;color:#7ee787}
.modebtn{display:flex;gap:6px}.modebtn button{flex:1}.modebtn button.on{background:#1f6feb}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}@media(max-width:680px){.grid2{grid-template-columns:1fr}}
.sw{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px dashed #30363d}
#convs{max-height:210px;overflow-y:auto;padding-right:4px;-webkit-overflow-scrolling:touch}
#convs::-webkit-scrollbar{width:5px}#convs::-webkit-scrollbar-thumb{background:#30363d;border-radius:3px}
.seg{display:inline-flex;border:1px solid #30363d;border-radius:8px;overflow:hidden;background:#0d1117}
.seg button{border:0;border-radius:0;background:transparent;color:#8b949e;padding:7px 16px;min-width:92px}
.seg button.on{background:#1f6feb;color:#fff}
.topuser{display:flex;align-items:center;gap:8px;font-size:13px}
.topuser button{padding:5px 10px;font-size:12px}
.hidden{display:none !important}
</style></head><body>
<header><h1>Moin 控制台 <span class="badge">纯接口 · 无扫码</span></h1><div class="topuser" id="topUser">初始化…</div></header>
<main>
<div class="card" id="loginCard"><h2>① 登录（手机号 + 短信验证码）</h2>
<div class="row"><input id="phone" placeholder="手机号" value="18053220144"><button onclick="loginSend()">获取验证码</button></div>
<div class="row"><input id="code" placeholder="6 位验证码"><button onclick="loginVerify()">提交登录</button></div>
<pre id="loginOut">—</pre></div>

<div class="card"><h2>② 账号 / 保活开关 <span id="keepState" class="tag">检测中…</span></h2>
<div id="acct">…</div>
<div class="row"><button class="warn" onclick="activate()">启用保活</button><button class="sec" onclick="stopKeep()">停止保活</button>
<button class="sec" onclick="keepTest()">🧪 保活功能测试</button>
<span id="keepState2" class="dim"></span></div>
<pre id="testOut" style="display:none;max-height:120px"></pre>
<div class="row"><span class="dim" style="min-width:88px">回答模式</span>
<div class="seg"><button id="m9" onclick="setMode(9)">云电脑</button><button id="m0" onclick="setMode(0)">对话</button></div>
<span class="tag" id="cloudMode">模式读取中…</span></div></div>

<div class="card"><h2>③ 会话列表 <span class="dim" style="font-size:12px">点开=查看历史+发消息+等回复</span></h2>
<div class="row"><button class="sec sm" onclick="newConv()">➕ 新建会话（按命名配置自动重命名）</button></div>
<div id="convs">…</div></div>

<div class="card"><h2>④ 配置（写进数据库，换账号登录记住）</h2>
<div class="grid2">
<div><div class="sw"><span>死亡自动新开会话</span><select id="autoNew" style="max-width:90px" onchange="saveSet('auto_new_on_dead',this.value)"><option value="0">关闭</option><option value="1">开启</option></select></div>
<div class="sw"><span>新会话命名前缀</span><input id="rnPrefix" style="max-width:110px" onchange="saveSet('rename_prefix',this.value)"></div>
<div class="sw"><span>命名后缀样式</span><select id="rnStyle" style="max-width:100px" onchange="saveSet('rename_style',this.value)"><option value="letter">A/B/C</option><option value="number">1/2/3</option></select></div>
<div class="sw"><span>当前计数</span><span id="rnCounter" class="dim">—</span></div></div>
<div><div class="sw"><span>小任务保活</span><span class="green">每 3–5 分钟随机一次</span></div>
<div class="dim" style="font-size:11px;padding:4px 0">固定规则：只发 99 乘法表 / 404 网页等沙箱小任务；隧道哨兵每秒检测、连续 3 秒失败立即拉起，与小任务无关。</div>
<div class="sw"><span>死亡关键词</span><input id="deathKw" style="max-width:200px" onchange="saveSet('death_keywords',this.value)"></div>
<div class="sw"><span>预览下一个名字</span><span id="rnPreview" class="green">—</span></div></div></div></div>

<div class="card"><h2>⑤ 历史登录</h2><div id="history">…</div></div>
<div class="card"><h2>⑥ 运行日志</h2><pre id="logbox">…</pre><button class="sec sm" onclick="loadLog()">刷新</button></div>
</main>

<div class="modal" id="modal"><div class="box"><h2 style="margin-top:0">首次登录 · 配置保活会话</h2>
<p>首次登录，选一个会话用于自动保活；<b>不选也行</b>，保活保持关闭。</p>
<select id="modalSel"></select><div class="row" style="margin-top:12px"><button onclick="modalSave()">保存并启用</button><button class="sec" onclick="modalSkip()">跳过</button></div></div></div>



<script>
let S={status:{},settings:{},cur:null};
function goConv(el){location.href='/chat?cid='+encodeURIComponent(el.getAttribute('data-cid'))}
async function api(p){const r=await fetch(p);return r.json()}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
async function refreshAll(){
  const st=await api('/api/status'); S.status=st; S.settings=st.settings||{};
  const svc=st.service==='active';
  const logged=st.logged_in!==false && !!st.account;
  document.getElementById('topUser').innerHTML=logged
    ? '<span class="ok">● 当前已登录：'+esc(st.account.name||st.account.uid)+'</span><button class="sec" onclick="logout()">退出登录</button>'
    : '<span class="bad">● 未登录</span><button class="sec" onclick="document.getElementById(\'loginCard\').classList.remove(\'hidden\')">登录</button>';
  document.getElementById('loginCard').classList.toggle('hidden', logged);
  const sub='<span class="dim" style="font-size:11px">小任务:'+(st.ka_pure==='active'?'开':'关')+' · 哨兵:'+(st.tunnel_watch==='active'?'开':'关')+'</span>';
  const ks=(svc?'<span class="ok">● 运行中</span>':'<span class="bad">● 已停止</span>')+' '+sub;
  document.getElementById('keepState').innerHTML='保活 '+ks;
  document.getElementById('keepState2').innerHTML='保活 '+ks;
  document.getElementById('acct').innerHTML=logged?
    '<div>UID <b>'+esc(st.account.uid)+'</b> · '+esc(st.account.phone||'')+'</div>'+
    '<div>保活会话: '+(st.account.keep_conv_id?'<span class="green">'+esc(st.account.keep_conv_name||st.account.keep_conv_id)+'</span>':'<span class="bad">未配置</span>')+'</div>':
    '<span class="bad">未登录</span>';
  // 模式
  const cm=st.cloud||{value:'0',label:'对话'};
  document.getElementById('cloudMode').innerText='当前: '+cm.label;
  document.getElementById('m9').className=cm.value==='9'?'on':'';document.getElementById('m0').className=cm.value==='0'?'on':'';
  // 会话列表
  document.getElementById('convs').innerHTML=(st.sessions||[]).map(c=>
    '<div class="conv '+(c.keep?'keep':'')+' '+(c.alive?'':'dead')+'" data-cid="'+esc(c.id)+'" onclick="goConv(this)">'+
    '<div><div class="nm">'+esc(c.name)+(c.keep?' <span class="pill keep">保活</span>':'')+'</div><div class="meta">'+esc(c.id)+' · 最后检查 '+(c.checked_at?new Date(c.checked_at*1000).toLocaleTimeString():'未检查')+'</div>'+
    (c.alive?'':'<div class="meta bad">☠️ '+esc(c.dead_reason||'已死亡')+'</div>')+'</div>'+
    '<span class="pill '+(c.alive?'live':'dead')+'">'+(c.alive?'存活':'死亡')+'</span></div>').join('')||'无';
  // 设置
  const set=S.settings;
  if(set.auto_new_on_dead!==undefined){
    document.getElementById('autoNew').value=set.auto_new_on_dead;
    document.getElementById('rnPrefix').value=set.rename_prefix||'';
    document.getElementById('rnStyle').value=set.rename_style||'letter';
    document.getElementById('deathKw').value=set.death_keywords||'';
    document.getElementById('rnCounter').innerText=set.rename_counter||'0';
    document.getElementById('rnPreview').innerText=set.next_name||'—';
  }
  const h=await api('/api/history');
  document.getElementById('history').innerHTML=h.map(x=>'<div class="hist" style="display:flex;justify-content:space-between;font-size:13px;padding:4px 0;border-bottom:1px dashed #30363d"><span>'+esc(x.name||x.uid)+' · '+esc(x.phone||'')+'</span><span class="dim">'+new Date(x.at*1000).toLocaleString()+'</span></div>').join('')||'无';
}
async function logout(){if(!confirm('退出当前登录？退出后可重新用手机号接验证码登录。'))return;await api('/api/logout');refreshAll()}
async function toggleAlive(cid,to){await api('/api/conv/'+(to?'alive':'dead')+'?cid='+encodeURIComponent(cid));refreshAll()}
async function saveSet(k,v){await api('/api/setting/set?key='+encodeURIComponent(k)+'&value='+encodeURIComponent(v));refreshAll()}
async function loginSend(){const r=await fetch('/api/login/send?phone='+encodeURIComponent(document.getElementById('phone').value));document.getElementById('loginOut').innerText=await r.text()}
async function loginVerify(){
  const r=await fetch('/api/login/verify?phone='+encodeURIComponent(document.getElementById('phone').value)+'&code='+encodeURIComponent(document.getElementById('code').value));
  const t=await r.text();document.getElementById('loginOut').innerText=t;
  let d={};try{d=JSON.parse(t)}catch(e){}
  if(d.ok){if(d.first_login){document.getElementById('modalSel').innerHTML='<option value="">（不选，保活关闭）</option>'+(S.status.sessions||[]).map(c=>'<option value="'+esc(c.id)+'">'+esc(c.name)+'</option>').join('');document.getElementById('modal').style.display='flex'}else refreshAll()}
}
async function modalSave(){const cid=document.getElementById('modalSel').value,d=JSON.parse(document.getElementById('loginOut').innerText);if(cid)await api('/api/keep/set?uid='+encodeURIComponent(d.uid)+'&cid='+encodeURIComponent(cid)+'&name='+encodeURIComponent((S.status.sessions||[]).find(s=>s.id===cid)?.name||''));document.getElementById('modal').style.display='none';await api('/api/keep/activate?uid='+encodeURIComponent(d.uid));refreshAll()}
async function modalSkip(){document.getElementById('modal').style.display='none';const d=JSON.parse(document.getElementById('loginOut').innerText);await api('/api/keep/activate?uid='+encodeURIComponent(d.uid));refreshAll()}
async function activate(){const d=S.status;if(!d.account){alert('未登录');return}await api('/api/keep/activate?uid='+encodeURIComponent(d.account.uid));refreshAll()}
async function stopKeep(){await api('/api/keep/stop');refreshAll()}
async function setMode(v){await api('/api/cloud_mode/set?v='+v);refreshAll()}
async function newConv(){const d=await api('/api/conv/new');if(d.need_manual){alert(d.hint)}else{alert('新建会话: '+d.conversation_id+' '+d.name)}refreshAll()}
async function keepTest(){
  const box=document.getElementById('testOut');box.style.display='block';box.innerText='测试启动：3秒「你好」→ 7秒「你好你好」→ 10秒「你好呀」…';
  await api('/api/keep/test');
  let n=0;const t=setInterval(async()=>{
    n++;const d=await api('/api/keep/test/result');
    box.innerText='进度:\n'+(d.results||[]).map(r=>r.at+'s  '+r.text+'  '+(r.ok?'✅ 已发送'+(r.reply?' 回复:'+r.reply:'')+(r.death?' ☠️'+r.death:''):'❌ 失败')).join('\n')+(d.running?'\n⏳ 等待下一次…':'\n✅ 测试完成');
    if(!d.running||n>14){clearInterval(t)}
  },1500);
}
async function loadLog(){const r=await fetch('/api/log');document.getElementById('logbox').innerText=await r.text()}
refreshAll();loadLog();setInterval(refreshAll,20000);
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def _send(self,obj,raw=False):
        b=(obj if raw else json.dumps(obj,ensure_ascii=False)).encode() if isinstance(obj,str) else json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(200);self.send_header("Content-Type","text/plain; charset=utf-8" if raw else "application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def do_GET(self):
        p=urllib.parse.urlparse(self.path);q=urllib.parse.parse_qs(p.query);g=lambda k,d="":q.get(k,[d])[0]
        try:
            if p.path=="/chat":
                b=CHATP.HTML.encode();self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8")
                self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
            elif p.path=="/":
                b=HTML.encode();self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8")
                self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
            elif p.path=="/api/logout":
                # 退出登录：停保活/哨兵，清空 active 与浏览器 cookie；保留账号库/历史/配置
                KEEP.stop_all()
                try: os.remove(ACTIVE_F)
                except Exception: pass
                try:
                    import websocket as _ws
                    v = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=5).read())
                    w = _ws.create_connection(v["webSocketDebuggerUrl"], timeout=10)
                    w.send(json.dumps({"id":1,"method":"Storage.clearCookies"}))
                    while True:
                        if json.loads(w.recv()).get("id")==1: break
                    w.close()
                except Exception: pass
                log.info("logout done")
                self._send({"ok":True})
            elif p.path=="/panel/go":
                e = panel_entrance()
                self.send_response(302)
                self.send_header("Location", "/panel" + e)
                self.send_header("Cache-Control","no-store")
                self.end_headers()
            elif p.path=="/api/status":
                st=status()
                try: st["cloud"]=json.loads(subprocess.run(["python3","/root/cloudmode.py"],capture_output=True,text=True,timeout=25).stdout.strip())
                except Exception: st["cloud"]={"value":"?","label":"?"}
                if uid():
                    s=DB.all_settings(uid());s["next_name"]=self._preview_name();st["settings"]=s
                self._send(st)
            elif p.path=="/api/history": self._send(DB.history())
            elif p.path=="/api/sessions": self._send(sessions_with_status())
            elif p.path=="/api/log":
                try:self._send("".join(open(LOG_F).readlines()[-40:]),raw=True)
                except Exception:self._send("(no log)",raw=True)
            elif p.path=="/api/cloud_mode/set":
                out=subprocess.run(["python3","/root/cloudmode.py",g("v","9")],capture_output=True,text=True,timeout=30).stdout.strip()
                self._send(out,raw=True)
            elif p.path=="/api/setting/set":
                DB.set_setting(uid(),g("key"),g("value"));self._send({"ok":True})
            elif p.path=="/api/login/send":
                log.info("send_code %s",g("phone"));self._send(LOGIN.send_code(g("phone")),raw=True)
            elif p.path=="/api/login/verify":
                phone,code=g("phone"),g("code");log.info("sms_login %s",phone)
                out=subprocess.run(["python3","/root/login_api.py","verify",phone,code],capture_output=True,text=True,timeout=90).stdout.strip()
                try:d=json.loads(out)
                except Exception:self._send(out,raw=True);return
                if d.get("ok"):
                    acc=DB.get_account(d["uid"]);first=acc is None or not acc["keep_conv_id"]
                    DB.upsert_account(d["uid"],d["name"],phone,d["cookie_file"],json.dumps(d["device"]))
                    d["first_login"]=first;log.info("login ok %s first=%s",d["uid"],first)
                self._send(d)
            elif p.path=="/api/keep/set": self._send(KEEP.set_keep(g("uid"),g("cid"),g("name")))
            elif p.path=="/api/keep/activate": self._send(KEEP.activate(g("uid")))
            elif p.path=="/api/keep/test":
                threading_ok = True
                # 用后台线程跑，接口立即返回
                import threading as _th
                def _run():
                    subprocess.run(["python3","/root/keep_test_worker.py"], capture_output=True, text=True, timeout=140)
                open("/root/keep_test_result.json","w").write(json.dumps({"ok":True,"running":True,"results":[]}))
                _th.Thread(target=_run, daemon=True).start()
                self._send({"ok":True,"started":True,"plan":[[3,"你好"],[7,"你好你好"],[10,"你好呀"]]})
            elif p.path=="/api/keep/test/result":
                try: self._send(open("/root/keep_test_result.json").read(), raw=True)
                except Exception: self._send('{"ok":false,"results":[]}', raw=True)
            elif p.path=="/api/keep/stop":
                self._send(KEEP.stop_all())
            elif p.path=="/api/keep/start":
                self._send(KEEP.start_all())
            elif p.path=="/api/conv/messages":
                msgs=API.single(g("cid"),30)
                self._send([{"me":m.get("sender_id")=="2328113677082323",
                             "text":m.get("tts_content") or m.get("content") or "",
                             "time":int(m.get("create_time") or 0)} for m in msgs])
            elif p.path=="/api/conv/status":
                cv=DB.get_conv(uid(),g("cid"));acc=DB.get_account(uid()) if uid() else None
                cv["keep"]=(acc and acc["keep_conv_id"]==g("cid"));self._send(cv)
            elif p.path=="/api/conv/send":
                sse=API.send_full(g("cid"),g("text"))
                hit=API.death_check(sse,DB.all_settings(uid())["death_keywords"]) if uid() else None
                if hit: DB.mark_dead(uid(),g("cid"),"网页发送命中: "+hit)
                self._send({"ok":True,"reply":API.extract_reply(sse)[:200],"death":hit})
            elif p.path=="/api/conv/alive": DB.mark_alive(uid(),g("cid"));self._send({"ok":True})
            elif p.path=="/api/conv/dead": DB.mark_dead(uid(),g("cid"),"用户手动标记");self._send({"ok":True})
            elif p.path=="/api/conv/rename":
                API.rename(g("cid"),g("name"));DB.upsert_conv(uid(),g("cid"),name=g("name"));self._send({"ok":True})
            elif p.path=="/api/conv/new":
                name=DB.next_conv_name(uid());new=API.create_conv_by_send(name)
                if new["conversation_id"]: DB.upsert_conv(uid(),new["conversation_id"],name,alive=1)
                self._send(new)
            else: self.send_response(404);self.end_headers()
        except Exception as e:
            log.exception("api error");self._send({"error":str(e)[:200]})
    def _preview_name(self):
        s=DB.all_settings(uid());prefix=s["rename_prefix"];n=int(s["rename_counter"] or 0)+1
        if s["rename_style"]=="number":suf=str(n)
        else:
            x=n-1;suf=""
            while True:
                suf=chr(65+x%26)+suf;x=x//26-1
                if x<0:break
        return prefix+"（"+suf+"）"

if __name__=="__main__":
    log.info("v3 管理台启动 :%d",PORT)
    ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()