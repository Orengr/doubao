#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
unified_lite.py — v3 管理台（纯 HTTP，无浏览器）

页面: 18800
  登录区: QR（纯 HTTP 拉取/轮询）+ 手机号短信（send_code 已通，提交待补）
  状态区: cookie 活性 / 隧道 / 保活
后端: ka_http.py 保活引擎
"""
import os, json, time, base64, logging, threading, subprocess
import urllib.request, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie

PORT = int(os.environ.get("PORT", "18800"))
CK = "/root/ck_full.txt"
QR_TOKEN_F = "/root/qr_token.json"
KA_STATE = "/root/ka_state.json"
CONF_F = "/root/keepconf.json"

BASE_ACC = "https://accounts.doubao.com"
Q_ACC = ("passport_jssdk_version=4.4.6&passport_jssdk_type=normal"
         "&is_from_ttaccountsdk=1&aid=497858&language=zh&account_app_language=en-US")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) HeadlessChrome/156.0.8078.4 Safari/537.36")

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("/root/unified_lite.log", encoding="utf-8"),
              logging.StreamHandler()])
log = logging.getLogger("lite")

STATE = {"qr": "", "qr_token": "", "qr_ts": 0, "login_status": "init"}

def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": "https://www.doubao.com/"})
    r = urllib.request.urlopen(req, timeout=timeout)
    return r.read().decode(errors="ignore"), r.headers

def qr_new():
    url = f"{BASE_ACC}/passport/web/get_qrcode/?next=https%3A%2F%2Fwww.doubao.com&{Q_ACC}"
    t, _ = http_get(url)
    d = json.loads(t).get("data", {})
    STATE["qr"] = d.get("qrcode", "")
    STATE["qr_token"] = d.get("token", "")
    STATE["qr_ts"] = time.time()
    return STATE["qr"], STATE["qr_token"]

def qr_check():
    tok = STATE.get("qr_token")
    if not tok: return {"status": "no_token"}
    url = (f"{BASE_ACC}/passport/web/check_qrconnect/?next=https%3A%2F%2Fwww.doubao.com"
           f"&token={tok}&{Q_ACC}")
    # 需要带 cookie jar 收 Set-Cookie
    req = urllib.request.Request(url, headers={"User-Agent": UA,
        "Referer": "https://www.doubao.com/"})
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k): return None
    opener = urllib.request.build_opener(NoRedirect)
    try:
        r = opener.open(req, timeout=15)
        body = r.read().decode(errors="ignore")
        headers = r.headers
        code = 200
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")
        headers = e.headers
        code = e.code
    d = {}
    try: d = json.loads(body)
    except Exception: pass
    # 状态: 1=待扫 2=已扫待确认 5=已确认(成功)
    st = str(d.get("data", {}).get("status", ""))
    out = {"status_code": st, "raw": json.dumps(d)[:200]}
    if st in ("5", "new"):
        # 成功: 从 Set-Cookie 收集
        setcks = headers.get_all("Set-Cookie") or []
        pairs = []
        for sc in setcks:
            c = SimpleCookie()
            try:
                c.load(sc)
                for k, morsel in c.items():
                    pairs.append(f"{k}={morsel.value}")
            except Exception: pass
        if pairs:
            txt = ";\n".join(pairs)
            bak = f"/root/ck_backups/ck_{time.strftime('%Y%m%d_%H%M%S')}.txt"
            os.makedirs("/root/ck_backups", exist_ok=True)
            try: open(bak,"w").write(txt)
            except Exception: pass
            open(CK, "w").write(txt)
            out["saved_cookies"] = len(pairs)
            out["login"] = True
            log.info(f"QR 登录成功，保存 {len(pairs)} 个 cookie")
    return out

def cookie_alive():
    """调 recent_conv 判断 ck_full.txt 是否有效"""
    ck = "; ".join(l.strip() for l in open(CK) if "=" in l) if os.path.exists(CK) else ""
    if not ck: return False, "no cookie"
    QS = ("version_code=20800&language=zh&device_platform=web&aid=497858"
          "&real_aid=497858&pkg_type=release_version")
    body = json.dumps({"cmd":3200,"uplink_body":{"pull_recent_conv_chain_uplink_body":{
        "conv_version":0,"limit":5,
        "filter":{"conversation_type":[],"project_filter":0,"device_filter":1},
        "message_count_per_conv":0,
        "option":{"not_need_message":True,"need_complete_conversation":True,
                  "need_coco_bot":True}}},
        "sequence_id":str(__import__('uuid').uuid4()),"channel":2,"version":"1"}).encode()
    req = urllib.request.Request(
        "https://www.doubao.com/im/chain/recent_conv?"+QS, data=body,
        headers={"Cookie":ck,"User-Agent":UA,"Referer":"https://www.doubao.com/",
                 "Content-Type":"application/json; encoding=utf-8"})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        d = json.loads(r.read().decode())
        uid = d.get("downlink_body",{}).get("pull_recent_conv_chain_downlink_body",{}).get("user_id","")
        if d.get("status_code")==0 and uid:
            return True, uid
        return False, f"status={d.get('status_code')}"
    except Exception as e:
        return False, str(e)[:80]

def tunnel_ok(url):
    try:
        r = urllib.request.urlopen(url+"/ping", timeout=3)
        return b"ok" in r.read(200)
    except Exception:
        return False

PAGE = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DoubaoBox · 控制台</title><style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,"PingFang SC",sans-serif;background:#0b0f19;color:#e8eefc;padding:18px 14px;max-width:720px;margin:0 auto}
h1{font-size:19px;margin:8px 0 14px}
.card{background:#121826;border:1px solid #243044;border-radius:14px;padding:16px;margin-bottom:14px}
.card h2{font-size:14px;color:#4d8dff;margin-bottom:10px}
button{background:#3b82f6;color:#fff;border:0;border-radius:10px;padding:11px 16px;font-size:14px;width:100%;margin:5px 0}
button.gray{background:#243044}
.st{font-size:13px;line-height:1.8;color:#9aa7bd}
img.qr{width:220px;height:220px;background:#fff;border-radius:10px;display:block;margin:10px auto}
.ok{color:#22c55e}.bad{color:#ef4444}
input{background:#1a2233;border:1px solid #243044;border-radius:8px;color:#fff;padding:10px;width:100%;font-size:14px;margin:5px 0}
.row{display:flex;gap:8px}.row>*{flex:1}
</style></head><body>
<h1>DoubaoBox 控制台 <span style="font-size:12px;color:#667">v3 纯HTTP</span></h1>

<div class="card">
<h2>登录</h2>
<div class="st" id="loginState">检测中…</div>
<div id="qrBox" style="display:none">
  <img class="qr" id="qrImg" alt="QR">
  <div style="text-align:center;font-size:12px;color:#667">用豆包/抖音 App 扫码</div>
</div>
<button onclick="newQr()">获取二维码</button>
<button class="gray" onclick="smsBoxToggle()">手机号短信登录（测试中）</button>
<div id="smsBox" style="display:none">
  <div class="row"><input id="phone" placeholder="手机号"></div>
  <button onclick="sendSms()">发送验证码</button>
  <div class="row"><input id="code" placeholder="6位验证码"></div>
  <button onclick="submitCode()">提交验证码</button>
</div>
</div>

<div class="card">
<h2>系统状态</h2>
<div class="st" id="sysState">加载中…</div>
</div>

<div class="card">
<h2>保活引擎 (ka_http)</h2>
<div class="st" id="kaState">加载中…</div>
<div class="row">
<button onclick="kaCtl('start')">启动</button>
<button class="gray" onclick="kaCtl('stop')">停止</button>
</div>
</div>

<div class="card">
<h2>关于</h2>
<div class="st" style="font-size:11.5px">仅供个人娱乐与技术学习，无任何攻击或侵权意图。<br>
数据存储于豆包沙箱持久卷。详见项目 LICENSE。</div>
</div>

<script>
async function post(u,d){
  try{const r=await fetch(u+'?t='+Date.now(),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d||{})});return await r.json()}
  catch(e){showErr('请求失败: '+e.message+'<br>备用地址: http://114.215.204.238/lite/');return {ok:false,err:e.message}}
}
async function get(u){
  try{const r=await fetch(u+'?t='+Date.now());return await r.json()}
  catch(e){showErr('请求失败: '+e.message+'<br>备用地址: http://114.215.204.238/lite/');return {err:e.message}}
}
function showErr(html){
  let el=document.getElementById('errBox');
  if(!el){el=document.createElement('div');el.id='errBox';el.className='card';document.body.prepend(el)}
  el.innerHTML='<h2 style="color:#ef4444">连接异常</h2><div class="st">'+html+'</div>';
}
async function newQr(){
  document.getElementById('loginState').innerText='正在获取二维码…';
  const d=await post('/api/qr_new');
  if(d.qr){document.getElementById('qrImg').src=d.qr;document.getElementById('qrBox').style.display='block';pollQr();}
  else document.getElementById('loginState').innerText='获取失败: '+(d.err||'');
}
async function pollQr(){
  const d=await post('/api/qr_check');
  if(d.login){document.getElementById('loginState').innerHTML='<span class="ok">✓ 登录成功（'+d.saved_cookies+' cookies）</span>';document.getElementById('qrBox').style.display='none';loadSys();return;}
  if(d.status_code==='2'){document.getElementById('loginState').innerText='已扫码，请在手机上确认…';}
  setTimeout(pollQr, 3000);
}
async function sendSms(){
  const d=await post('/api/sms_send',{phone:document.getElementById('phone').value});
  alert(d.ok?('验证码已发送':'失败: '+d.err));
}
async function submitCode(){
  const d=await post('/api/sms_submit',{phone:document.getElementById('phone').value,code:document.getElementById('code').value});
  if(d.login){document.getElementById('loginState').innerHTML='<span class="ok">✓ 登录成功</span>';}else alert('失败: '+d.err);
}
function smsBoxToggle(){const b=document.getElementById('smsBox');b.style.display=b.style.display==='none'?'block':'none'}
async function loadSys(){
  const d=await get('/api/status');
  document.getElementById('loginState').innerHTML = d.cookie_alive
    ? '<span class="ok">✓ cookie 有效 (uid:'+d.uid+')</span>'
    : '<span class="bad">✗ cookie 无效/未登录</span>';
  document.getElementById('sysState').innerHTML =
    '控制面隧道: '+(d.tunnel_ctl?'<span class="ok">✓</span>':'<span class="bad">✗</span>')+
    ' · 1Panel隧道: '+(d.tunnel_panel?'<span class="ok">✓</span>':'<span class="bad">✗</span>');
  document.getElementById('kaState').innerHTML =
    '运行: '+d.ka_running+' · 熔断: '+d.ka_stopped+' · 失败连击: '+d.ka_fail;
}
async function kaCtl(a){
  const d=await post('/api/ka_ctl',{action:a});
  alert(d.ok?'已'+a:'失败: '+(d.err||''));loadSys();
}
loadSys();setInterval(loadSys,15000);
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"   # 手机浏览器需要；配合 Content-Length 的 keep-alive

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        b = body.encode() if isinstance(body,str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Connection", "close")   # 每次显式关闭，避免手机端挂起
        self.end_headers()
        try: self.wfile.write(b)
        except Exception: pass
        try: self.close_connection = True
        except Exception: pass
    def _json(self, d): self._send(200, json.dumps(d, ensure_ascii=False))
    def log_message(self, *a): pass

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p in ("/", "/index.html"):
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if p == "/api/status":
            alive, info = cookie_alive()
            ka = {}
            try: ka = json.load(open(KA_STATE))
            except Exception: pass
            running = subprocess.run(["systemctl","is-active","moin-ka-http"],
                capture_output=True,text=True).stdout.strip()=="active"
            return self._json({"cookie_alive": alive, "uid": str(info)[:20],
                "tunnel_ctl": tunnel_ok("http://127.0.0.1:17800"),
                "tunnel_panel": tunnel_ok("http://127.0.0.1:18090"),
                "ka_running": running, "ka_stopped": ka.get("stopped",False),
                "ka_fail": ka.get("fail_streak",0)})
        return self._json({"err":"not found"})

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        ln = int(self.headers.get("Content-Length","0") or 0)
        body = {}
        try: body = json.loads(self.rfile.read(ln)) if ln else {}
        except Exception: pass
        if p == "/api/qr_new":
            try:
                qr, tok = qr_new()
                return self._json({"ok": True, "qr": qr, "token": tok})
            except Exception as e:
                return self._json({"ok": False, "err": str(e)[:100]})
        if p == "/api/qr_check":
            try: return self._json(qr_check())
            except Exception as e: return self._json({"err": str(e)[:100]})
        if p == "/api/sms_send":
            # send_code 已验证接口；mobile 混淆
            ph = (body.get("phone") or "").strip()
            if not ph: return self._json({"ok": False, "err": "手机号为空"})
            plain = ("+86 " + ph).encode()
            enc = "".join(f"{b^5:02x}" for b in plain)
            url = (f"{BASE_ACC}/passport/web/send_code/?{Q_ACC}"
                   f"&ts={int(time.time())}&p_ca=4.0.26&multi_login=1&account_sdk_source=web")
            data = urllib.parse.urlencode({"mix_mode":"1","mobile":enc,"type":"3731",
                "is6Digits":"1","fixed_mix_mode":"1"}).encode()
            req = urllib.request.Request(url, data=data, headers={
                "User-Agent": UA, "Referer": "https://www.doubao.com/",
                "Content-Type": "application/x-www-form-urlencoded"})
            try:
                r = urllib.request.urlopen(req, timeout=15)
                t = r.read().decode()[:200]
                return self._json({"ok": True, "resp": t})
            except Exception as e:
                return self._json({"ok": False, "err": str(e)[:100]})
        if p == "/api/sms_submit":
            return self._json({"ok": False,
                "err": "验证码提交接口待补（需要真实手机号触发一次）"})
        return self._json({"err":"not found"})

class Server(ThreadingHTTPServer):
    request_queue_size = 128      # 手机浏览器并发连接多，默认5太小
    daemon_threads = True
    allow_reuse_address = True

if __name__ == "__main__":
    log.info(f"unified_lite 启动 :{PORT}")
    Server(("0.0.0.0", PORT), H).serve_forever()
