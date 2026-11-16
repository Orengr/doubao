#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""moin_api_console.py v3 — 18800 纯接口管理台"""
import json, os, time, subprocess, urllib.request, urllib.parse, logging, sys, base64
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

PANEL_TOKEN = "oms2rROVaDd8t8s9jWIYKBW1eYREoQbu"
CTL_BASE = "http://127.0.0.1:17800"
PANEL_FALLBACK = "/cSK41ajJX5"

def sbx_sh(cmd, timeout=120):
    try:
        url = CTL_BASE + "/sh?token=" + PANEL_TOKEN + "&t=" + str(timeout)
        req = urllib.request.Request(url, data=cmd.encode(), method="POST")
        with urllib.request.urlopen(req, timeout=timeout + 15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"rc": -1, "out": "ERR: " + str(e)[:200]}

def sbx_bg(name, cmd):
    b64 = base64.b64encode(cmd.encode()).decode()
    sc = ("mkdir -p /home/user/.dsh_pend/log && echo " + b64 + " | base64 -d > /home/user/.dsh_pend/" + name + ".sh && chmod +x /home/user/.dsh_pend/" + name + ".sh && cd /home/user/.dsh_pend && setsid nohup bash " + name + ".sh >/dev/null 2>&1 </dev/null & echo STARTED")
    return sbx_sh(sc, 30)

def panel_entrance():
    try:
        url = CTL_BASE + "/get?token=" + PANEL_TOKEN + "&p=/home/user/.dsh_pend/state/panel_entrance.txt"
        e = urllib.request.urlopen(url, timeout=8).read().decode("utf-8", "ignore").strip()
        if e.startswith("/") and len(e) < 40: return e
    except Exception: pass
    return PANEL_FALLBACK


AGENT = "http://127.0.0.1:17801"

def agent_get(path):
    try:
        u = AGENT + path + ("&" if "?" in path else "?") + "token=" + PANEL_TOKEN
        with urllib.request.urlopen(u, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": "agent: " + str(e)[:150]}

def agent_post(path, body):
    try:
        u = AGENT + path + "?token=" + PANEL_TOKEN
        req = urllib.request.Request(u, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": "agent: " + str(e)[:150]}

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

PANEL_HTML = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0b0f19"><title>Moin 面板</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
:root{--bg:#0b0f19;--card:#121826;--card2:#1a2233;--line:#243044;--txt:#e8eefc;--dim:#7f8da8;--ok:#3ddc97;--warn:#ffb648;--err:#ff5c7c;--acc:#4d8dff;--acc2:#7c5cff}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--txt);font-size:14px;line-height:1.6;overflow-x:hidden}
.top{position:fixed;top:0;left:0;right:0;height:52px;z-index:30;background:rgba(11,15,25,.98);backdrop-filter:blur(10px);border-bottom:1px solid var(--line);display:flex;align-items:center;gap:12px;padding:0 14px}
.burger{width:34px;height:34px;display:grid;place-items:center;cursor:pointer;border-radius:9px;flex:none}
.burger:active{background:var(--card2)}
.burger span{display:block;width:17px;height:2px;background:var(--txt);border-radius:2px;position:relative;transition:.25s}
.burger span::before,.burger span::after{content:"";position:absolute;left:0;width:17px;height:2px;background:var(--txt);border-radius:2px;transition:.25s}
.burger span::before{top:-5.5px}.burger span::after{top:5.5px}
body.menu .burger span{background:transparent}
body.menu .burger span::before{top:0;transform:rotate(45deg)}
body.menu .burger span::after{top:0;transform:rotate(-45deg)}
.top h1{font-size:15.5px;font-weight:700;flex:1}
.live{display:flex;align-items:center;gap:5px;font-size:11.5px;color:var(--dim)}
.dot{width:7px;height:7px;border-radius:50%;background:var(--ok);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.55;transform:scale(.85)}}
.dot.err{background:var(--err);animation:none}
.side{position:fixed;top:0;left:0;bottom:0;width:230px;background:#0f1520;border-right:1px solid var(--line);z-index:40;transform:translateX(-100%);transition:.28s cubic-bezier(.4,0,.2,1);padding-top:14px;overflow-y:auto}
body.menu .side{transform:translateX(0);box-shadow:8px 0 32px rgba(0,0,0,.5)}
.mask{position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:35;opacity:0;pointer-events:none;transition:.25s}
body.menu .mask{opacity:1;pointer-events:auto}
.side .brand{padding:6px 18px 16px;display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--line);margin-bottom:8px}
.side .brand .lg{width:32px;height:32px;border-radius:10px;background:linear-gradient(135deg,var(--acc),var(--acc2));display:grid;place-items:center;font-weight:700}
.side .brand b{font-size:14.5px}.side .brand small{display:block;font-size:10.5px;color:var(--dim);font-weight:400}
.nav{padding:6px 10px}
.nav a{display:flex;align-items:center;gap:11px;padding:10px 12px;border-radius:9px;color:#b6c2d9;font-size:13.5px;text-decoration:none;margin-bottom:2px;cursor:pointer}
.nav a .i{width:20px;text-align:center;opacity:.85;font-size:15px}
.nav a.on{background:var(--card2);color:var(--txt);font-weight:600}
.nav a:active{background:var(--card2)}
.nav .grp{font-size:10.5px;color:var(--dim);padding:12px 12px 5px;letter-spacing:1px}
main{padding:66px 14px 24px;max-width:900px;margin:0 auto}
h2{font-size:12.5px;color:var(--dim);letter-spacing:.9px;text-transform:uppercase;margin:18px 0 10px;font-weight:600;display:flex;justify-content:space-between;align-items:center}
h2:first-child{margin-top:0}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
@media(min-width:700px){.grid{grid-template-columns:repeat(4,1fr)}}
.card{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:14px}
.kpi{position:relative;overflow:hidden}
.kpi .v{font-size:21px;font-weight:700;font-variant-numeric:tabular-nums;letter-spacing:-.5px}
.kpi .k{font-size:11.5px;color:var(--dim);margin-top:1px}
.kpi .sub{font-size:10.5px;color:var(--dim);margin-top:6px;opacity:.8}
.ring{width:44px;height:44px;position:absolute;right:12px;top:50%;transform:translateY(-50%)}
.ring svg{transform:rotate(-90deg)}
.ring circle{fill:none;stroke-width:4;stroke-linecap:round}
.ring .bgc{stroke:var(--card2)}
.ring .fgc{stroke:var(--acc);transition:stroke-dasharray .5s}
.ring .txt{position:absolute;inset:0;display:grid;place-items:center;font-size:9.5px;color:var(--dim)}
.bar{height:7px;background:var(--card2);border-radius:4px;overflow:hidden;margin-top:9px}
.bar i{display:block;height:100%;border-radius:4px;background:linear-gradient(90deg,var(--acc),var(--acc2));transition:width .55s ease}
.bar.warn i{background:linear-gradient(90deg,var(--warn),#ff8a3d)}
.bar.err i{background:linear-gradient(90deg,var(--err),#ff3d6e)}
.row{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--line);font-size:13px;gap:10px}
.row:last-child{border:0}
.row .k{color:var(--dim);font-size:12.5px;flex:none}
.row .v{font-weight:600;text-align:right;word-break:break-all;font-size:12.5px}
.ok{color:var(--ok)}.err{color:var(--err)}.warn{color:var(--warn)}.dim{color:var(--dim)}
.pill{font-size:11px;padding:2px 9px;border-radius:8px;white-space:nowrap;font-weight:600}
.pill.ok{background:rgba(61,220,151,.15);color:var(--ok)}
.pill.err{background:rgba(255,92,124,.15);color:var(--err)}
button{background:var(--acc);border:0;color:#fff;padding:9px 15px;border-radius:9px;font-size:13px;cursor:pointer;font-weight:500}
button.sec{background:var(--card2);border:1px solid var(--line);color:var(--txt)}
button.sm{padding:5px 11px;font-size:12px}
button:active{transform:scale(.97)}
input,textarea,select{background:#0d1117;border:1px solid var(--line);color:var(--txt);padding:10px 12px;border-radius:9px;font-size:13px;width:100%;font-family:inherit;outline:none}
input:focus,textarea:focus{border-color:var(--acc)}
pre{background:#0d1117;border:1px solid var(--line);border-radius:10px;padding:12px;overflow:auto;max-height:50vh;font-size:11.5px;color:#9fb0c9;white-space:pre-wrap;word-break:break-all;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.fitem{display:flex;align-items:center;gap:11px;padding:11px 0;border-bottom:1px solid var(--line);font-size:13px;cursor:pointer}
.fitem:last-child{border:0}
.fitem .ico{width:27px;height:27px;border-radius:8px;background:var(--card2);display:grid;place-items:center;font-size:12px;flex:none}
.fitem .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fitem .sz{font-size:11px;color:var(--dim);flex:none}
.toolbar{display:flex;gap:8px;margin-bottom:11px}
.toolbar input{flex:1}
.hide{display:none}
.tip{font-size:11.5px;color:var(--dim);padding:6px 0}
@media(max-width:420px){main{padding:64px 11px 20px}.grid{gap:8px}.card{padding:12px}}
</style></head><body>
<div class="top"><div class="burger" onclick="toggleMenu()"><span></span></div><h1 id="pageTitle">概览</h1>
<div class="live"><span class="dot" id="liveDot"></span><span id="liveTxt">实时</span></div></div>
<div class="mask" onclick="toggleMenu()"></div>
<div class="side">
  <div class="brand"><div class="lg">M</div><div><b>Moin 面板</b><small id="hostSm">豆包沙箱</small></div></div>
  <div class="nav" id="nav"></div>
</div>
<main id="view"><div class="card dim">加载中…</div></main>
<script>
var NAV=[["overview","概览","◉","监控"],["health","服务健康","◈","监控"],["phpinfo","PHP 环境","◐","监控"],["sessions","豆包会话","◧","监控"],["files","文件管理","▤","运维"],["disk","磁盘占用","◪","运维"],["sites","网站","◎","建站"],["databases","数据库","▦","建站"],["ftp","FTP 账户","⇄","建站"],["cron","计划任务","⏱","运维"],["procs","进程","▣","运维"],["containers","容器应用","▢","运维"],["backup","备份","⇩","运维"],["terminal","终端","＞","运维"]];
var cur="overview",S={},es=null;
function agentErr(o){var m=(o&&(o.error||o.detail))||'沙箱暂时离线';return '沙箱未连接：'+m+'（实例可能正在重建，约20秒后自动恢复）'}
function esc(s){return (s==null?"":String(s)).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
function fmtU(s){if(!s)return"—";var d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return d>0?d+"天"+h+"时":(h>0?h+"时"+m+"分":m+"分"+(Math.floor(s%60))+"秒")}
function fmtSz(b){if(!b)return"0";var u=["B","K","M","G","T"],i=0;while(b>=1024&&i<4){b/=1024;i++}return b.toFixed(i?1:0)+u[i]}
function barCls(p){p=parseFloat(p)||0;return p>85?"err":(p>70?"warn":"")}
async function api(p,opt){var r=await fetch(p,opt);var t=await r.text();try{return JSON.parse(t)}catch(e){return t}}
function toggleMenu(){document.body.classList.toggle('menu')}
function renderNav(){var g="",h="";NAV.forEach(function(x){if(x[3]!==g){g=x[3];h+='<div class="grp">'+g+'</div>'}h+='<a class="'+(x[0]===cur?'on':'')+'" data-k="'+x[0]+'"><span class="i">'+x[2]+'</span>'+x[1]+'</a>'});var n=document.getElementById('nav');n.innerHTML=h;n.querySelectorAll('a[data-k]').forEach(function(a){a.onclick=function(){go(a.getAttribute('data-k'))}})}
function go(k){cur=k;var t=NAV.filter(function(x){return x[0]===k})[0];document.getElementById('pageTitle').textContent=t?t[1]:k;renderNav();document.body.classList.remove('menu');load()}
function setLive(ok){var d=document.getElementById('liveDot');d.className='dot'+(ok?'':' err');document.getElementById('liveTxt').textContent=ok?'实时':'断开'}
async function load(){
  var v=document.getElementById('view');
  try{
    if(cur==='overview'){S.ov=await api('/api/panel/overview');if(!S.ov||!S.ov.host)throw new Error(agentErr(S.ov));v.innerHTML=ovHTML(S.ov)}
    else if(cur==='health'){S.h=await api('/api/panel/services');if(!Array.isArray(S.h))throw new Error(agentErr(S.h));v.innerHTML=healthHTML(S.h)}
    else if(cur==='files'){await files('')}
    else if(cur==='sites'){S.s=await api('/api/panel/sitelist');if(!Array.isArray(S.s))throw new Error(agentErr(S.s));v.innerHTML=sitesHTML(S.s);bindSiteActions()}
    else if(cur==='databases'){S.d=await api('/api/panel/databases');if(!Array.isArray(S.d))throw new Error(agentErr(S.d));v.innerHTML=dbHTML(S.d)}
    else if(cur==='procs'){S.p=await api('/api/panel/procs');if(!Array.isArray(S.p))throw new Error(agentErr(S.p));v.innerHTML=procsHTML(S.p)}
    else if(cur==='containers'){S.c=await api('/api/panel/containers');if(!Array.isArray(S.c))throw new Error(agentErr(S.c));v.innerHTML=contHTML(S.c)}
    else if(cur==='cron'){S.cr=await api('/api/panel/cron');if(!Array.isArray(S.cr))throw new Error(agentErr(S.cr));v.innerHTML=cronHTML(S.cr)}
    else if(cur==='sessions'){S.ss=await api('/api/panel/sessions');if(!Array.isArray(S.ss))throw new Error(agentErr(S.ss));v.innerHTML=sessionHTML(S.ss)}
    else if(cur==='phpinfo'){S.ph=await api('/api/panel/phpinfo');if(!S.ph||!S.ph.ok)throw new Error(agentErr(S.ph));v.innerHTML=phpHTML(S.ph)}
    else if(cur==='disk'){S.dk=await api('/api/panel/disk');if(!Array.isArray(S.dk))throw new Error(agentErr(S.dk));v.innerHTML=diskHTML(S.dk)}
    else if(cur==='backup'){v.innerHTML=backupHTML()}
    else if(cur==='ftp'){v.innerHTML=ftpHTML()}
    else if(cur==='terminal'){v.innerHTML=termHTML();bindTerm()}
  }catch(e){v.innerHTML='<div class="card err">加载失败: '+esc(e.message)+'</div>'}
}
function ring(p,label){
  var r=17,c=2*Math.PI*r,off=c*(1-p/100);
  var col=p>85?'#ff5c7c':(p>70?'#ffb648':'#4d8dff');
  return '<div class="ring"><svg width="44" height="44"><circle class="bgc" cx="22" cy="22" r="'+r+'"/><circle class="fgc" cx="22" cy="22" r="'+r+'" stroke="'+col+'" stroke-dasharray="'+c+'" stroke-dashoffset="'+off+'"/></svg><div class="txt">'+Math.round(p)+'%</div></div>';
}
function ovHTML(o){
  var mp=o.mem_total_mb?Math.round(o.mem_used_mb/o.mem_total_mb*100):0;
  var dp=parseFloat(o.disk_pct)||0;
  return '<h2>系统概览 <span class="dim" style="text-transform:none;letter-spacing:0;font-weight:400" id="ovTime">'+new Date().toLocaleTimeString()+'</span></h2>'
   +'<div class="grid">'
   +'<div class="card kpi"><div class="v" id="kCpu">'+o.cpu_cores+'</div><div class="k">CPU 核心</div><div class="sub" id="kLoad">负载 '+esc((o.load||"0 0 0").split(" ")[0])+'</div></div>'
   +'<div class="card kpi"><div class="v" id="kMem">'+o.mem_used_mb+'<span style="font-size:12px;color:var(--dim)">M</span></div><div class="k">内存已用</div>'+ring(mp)+'</div>'
   +'<div class="card kpi"><div class="v" id="kDisk">'+esc(o.disk_used)+'</div><div class="k">磁盘已用</div>'+ring(dp)+'</div>'
   +'<div class="card kpi"><div class="v" id="kUp">'+fmtU(o.uptime_sec)+'</div><div class="k">运行时长</div><div class="sub" id="kProc">'+o.procs+' 进程</div></div>'
   +'</div>'
   +'<h2>资源占用</h2><div class="card">'
   +'<div class="row"><span class="k">内存</span><span class="v" id="memTxt">'+o.mem_used_mb+'M / '+o.mem_total_mb+'M</span></div>'
   +'<div class="bar '+barCls(mp)+'"><i id="memBar" style="width:'+mp+'%"></i></div>'
   +'<div class="row" style="border:0;padding-top:11px"><span class="k">磁盘 (10T 持久卷)</span><span class="v" id="diskTxt">'+esc(o.disk_used)+' / '+esc(o.disk_total)+'</span></div>'
   +'<div class="bar '+barCls(dp)+'"><i id="diskBar" style="width:'+dp+'%"></i></div>'
   +'</div>'
   +'<h2>主机</h2><div class="card">'
   +'<div class="row"><span class="k">主机名</span><span class="v" id="hHost">'+esc(o.host)+'</span></div>'
   +'<div class="row"><span class="k">系统</span><span class="v">'+esc(o.os.replace(/PRETTY_NAME=|NAME=|"/g,"").split(" ").slice(0,3).join(" "))+'</span></div>'
   +'<div class="row"><span class="k">内核</span><span class="v">'+esc(o.kernel)+'</span></div>'
   +'<div class="row"><span class="k">平均负载</span><span class="v" id="hLoad">'+esc(o.load)+'</span></div>'
   +'</div>';
}
function healthHTML(h){
  var bad=h.filter(function(x){return !x.ok}).length;
  return '<h2>服务健康 '+(bad?'<span class="err">'+bad+' 项异常</span>':'<span class="ok">全部正常</span>')+'</h2><div class="card" id="hBox">'
   +h.map(function(x){return '<div class="row"><span class="k">'+esc(x.name)+'</span><span class="pill '+(x.ok?'ok':'err')+'">'+(x.ok?'正常':'异常')+'</span></div>'}).join('')
   +'</div><div style="margin-top:12px"><button class="sec sm" onclick="load()">立即检测</button></div>';
}
async function files(p){
  var d=await api('/api/panel/ls?p='+encodeURIComponent(p||''));
  var up=p?d.path.split('/').slice(0,-1).join('/'):'';
  document.getElementById('view').innerHTML=
   '<div class="toolbar"><input id="fp" value="'+esc(d.path)+'"><button class="sm" id="fpGo">打开</button></div>'
   +'<div class="card">'+(p?'<div class="fitem" data-p="'+esc(up)+'"><div class="ico">↑</div><div class="nm">.. 上级目录</div></div>':'')
   +d.items.map(function(i){var full=d.path.replace(/\/$/,'')+'/'+i.name;return '<div class="fitem" onclick="'+(i.dir?'files('+JSON.stringify(full)+')':'openFile('+JSON.stringify(full)+')')+'"><div class="ico">'+(i.dir?'▸':'▤')+'</div><div class="nm">'+esc(i.name)+'</div><div class="sz">'+(i.dir?'':fmtSz(i.size))+'</div></div>'}).join('')
   +'</div><pre id="fileview" class="hide"></pre>';
  var gb=document.getElementById('fpGo'); if(gb) gb.onclick=function(){files(document.getElementById('fp').value)};
  document.querySelectorAll('.fitem[data-p]').forEach(function(el){el.onclick=function(){files(el.getAttribute('data-p'))}});
}
async function openFile(p){var c=await api('/api/panel/read?p='+encodeURIComponent(p));var el=document.getElementById('fileview');el.classList.remove('hide');el.textContent=c;el.scrollIntoView({behavior:'smooth'})}
function sitesHTML(s){
  var rows = s.length ? s.map(function(x){
    var dom = (x.domains&&x.domains.length)?x.domains.join(", "):"未绑定域名";
    return '<div class="card" style="margin-bottom:9px"><div class="row"><span class="k">'+esc(x.name)+'</span><span class="pill '+(x.running?"ok":"err")+'">'+(x.running?"运行":"停")+'</span></div>'
      +'<div class="row"><span class="k">域名</span><span class="v dim">'+esc(dom)+'</span></div>'
      +'<div class="row"><span class="k">SSL</span><span class="v">'+(x.ssl?'<span class="ok">已开启</span>':'<span class="dim">未开启</span>')+'</span></div>'
      +'<div class="row"><span class="k">反向代理</span><span class="v">'+(x.proxy?'<span class="ok">是</span>':'<span class="dim">否</span>')+'</span></div>'
      +'<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:10px">'
      +'<button class="sec sm" data-act="domain" data-name="'+esc(x.name)+'">绑定域名</button>'
      +'<button class="sec sm" data-act="ssl" data-name="'+esc(x.name)+'">开 SSL</button>'
      +'<button class="sec sm" data-act="proxy" data-name="'+esc(x.name)+'">反代</button>'
      +'<button class="sec sm" data-act="log" data-name="'+esc(x.name)+'">日志</button>'
      +'<button class="sec sm" data-act="del" data-name="'+esc(x.name)+'">删除</button>'
      +'</div></div>';
  }).join("") : '<div class="card dim">暂无站点，下面新建一个</div>';
  return '<h2>网站 ('+s.length+')</h2>'+rows
   +'<h2>新建网站</h2><div class="card"><input id="sname" placeholder="站点名，如 blog"><div style="margin-top:9px"><button id="siteNew">创建站点</button></div><div class="tip">创建后目录在持久卷 www/站点名，自动生成 nginx 配置</div></div>'
   +'<pre id="sout" class="hide"></pre>';
}
function bindSiteActions(){
  var nb=document.getElementById("siteNew"); if(nb) nb.onclick=createSite;
  document.querySelectorAll("button[data-act]").forEach(function(b){
    b.onclick=function(){ siteAct(b.getAttribute("data-act"), b.getAttribute("data-name")); };
  });
}
async function siteAct(act,name){
  var el=document.getElementById("sout");
  if(!el) return;
  if(act==="del"){ if(!confirm("确认删除站点 "+name+"?"))return; }
  var body=null,url="";
  if(act==="domain"){ var d=prompt("输入要绑定的域名，如 blog.example.com"); if(!d)return; body={name:name,domain:d}; url="/api/panel/site_add_domain"; }
  else if(act==="ssl"){ body={name:name,enable:true}; url="/api/panel/site_ssl"; }
  else if(act==="proxy"){ var t=prompt("输入后端地址，如 http://127.0.0.1:8080"); if(!t)return; body={name:name,target:t}; url="/api/panel/site_proxy"; }
  else if(act==="log"){ el.classList.remove("hide"); el.textContent="读取日志…"; var r=await api("/api/panel/site_log?name="+encodeURIComponent(name)+"&n=60"); el.textContent=r.lines||r.error||JSON.stringify(r); return; }
  else if(act==="del"){ body={name:name}; url="/api/panel/site_delete"; }
  el.classList.remove("hide"); el.textContent="执行中…";
  var r=await api(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  el.textContent=JSON.stringify(r,null,2);
  var rl=await api("/api/panel/nginx_reload",{method:"POST"});
  el.textContent += "\n\nnginx: "+JSON.stringify(rl);
  await load();
}
async function createSite(){
  var n=document.getElementById("sname").value.trim(); if(!n)return;
  var r=await api("/api/panel/site_create",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:n})});
  var el=document.getElementById("sout"); el.classList.remove("hide"); el.textContent=JSON.stringify(r,null,2);
  await load();
}
function dbHTML(d){
  var rows=d.length?d.map(function(x){return '<div class="row"><span class="k">'+esc(x)+'</span><span class="v dim" onclick="dbTables('+JSON.stringify(x)+')">查看表</span></div>'}).join(''):'<div class="dim">暂无数据库</div>';
  return '<h2>MySQL 8.0 ('+d.length+')</h2><div class="card">'+rows+'</div>'
   +'<h2>新建数据库</h2><div class="card"><input id="newdb" placeholder="库名，如 myapp"><div style="margin-top:9px"><button onclick="createDB()">创建</button></div></div><pre id="dbout" class="hide"></pre>';
}
async function dbTables(db){var t=await api('/api/panel/tables?db='+encodeURIComponent(db));var el=document.getElementById('dbout');el.classList.remove('hide');el.textContent=db+' 的表 ('+t.length+'):\n'+(t.length?t.join('\n'):'(空)')}
async function createDB(){var n=document.getElementById('newdb').value.trim();if(!n)return;var sql='CREATE DATABASE IF NOT EXISTS '+n.replace(/[^A-Za-z0-9_]/g,'');var r=await api('/api/panel/dbquery?q='+encodeURIComponent(sql));var el=document.getElementById('dbout');el.classList.remove('hide');el.textContent=JSON.stringify(r);load()}
function procsHTML(p){
  return '<h2>进程 Top '+p.length+'</h2><div class="card">'+p.map(function(x){return '<div class="row"><span class="k">'+esc(x.name)+' <span class="dim">#'+x.pid+'</span></span><span class="v dim">'+x.cpu+'% · '+x.rss_mb+'M</span></div>'}).join('')+'</div>';
}
function contHTML(c){
  return '<h2>容器应用 (proot 隔离)</h2><div class="card">'+(c.length?c.map(function(x){return '<div class="row"><span class="k">#'+esc(x.pid)+'</span><span class="v dim">'+esc(x.cmd)+'</span></div>'}).join(''):'<div class="dim">暂无运行中的应用</div>')+'</div>'
   +'<h2>启动应用</h2><div class="card"><div style="margin-bottom:8px"><input id="cn" placeholder="应用名，如 web1"></div><div style="margin-bottom:8px"><input id="cr" placeholder="rootfs 路径（可选）"></div><div style="margin-bottom:10px"><input id="cc" placeholder="命令，如 python3 -m http.server 8080"></div><button onclick="runC()">启动</button></div><pre id="cout" class="hide"></pre>';
}
async function runC(){var b={name:document.getElementById('cn').value||'app',rootfs:document.getElementById('cr').value||'',cmd:document.getElementById('cc').value||'/bin/sh'};var r=await api('/api/panel/run_container',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});var el=document.getElementById('cout');el.classList.remove('hide');el.textContent=JSON.stringify(r,null,2)}
function sessionHTML(list){
  if(!list.length) return '<div class="card dim">没有会话</div>';
  var alive=0; for(var i=0;i<list.length;i++){ if(list[i].alive) alive++; }
  var rows = list.map(function(x){
    var badge = x.alive ? '<span class="pill ok">存活</span>' : '<span class="pill err">空</span>';
    var keep = x.keep ? '<span class="pill" style="background:rgba(77,141,255,.15);color:#4d8dff">保活</span>' : '';
    return '<div class="card" style="margin-bottom:9px"><div class="row"><span class="k">'+esc(x.name)+'</span>'+keep+badge+'</div>'
      +'<div class="row"><span class="k">会话ID</span><span class="v dim" style="font-size:11px">'+esc(x.conv_id)+'</span></div>'
      +'<div class="row"><span class="k">消息数</span><span class="v">'+x.msg_count+'</span></div>'
      +'</div>';
  }).join('');
  return '<h2>豆包会话 ('+list.length+' 个，'+alive+' 存活)</h2>'+rows;
}
function phpHTML(p){
  return '<h2>PHP 环境</h2><div class="card">'
   +'<div class="row"><span class="k">版本</span><span class="v">'+esc((p.version||"").split("\n")[0])+'</span></div>'
   +'<div class="row"><span class="k">二进制</span><span class="v dim">server/php/bin/php</span></div>'
   +'</div>'
   +'<h2>已加载模块 ('+(p.modules||[]).length+')</h2><div class="card">'
   +(p.modules||[]).map(function(m){return '<div class="row"><span class="v">'+esc(m)+'</span></div>'}).join('')
   +'</div>';
}
function diskHTML(d){
  var total=0;
  d.forEach(function(x){ var s=(x[0]||"").trim(); if(/G$/.test(s)) total+=parseFloat(s)*1024; else if(/M$/.test(s)) total+=parseFloat(s); });
  return '<h2>持久卷占用 (<span class="dim">'+d.length+' 项</span>)</h2><div class="card">'
   +d.map(function(x){
     var size=(x[0]||"").trim(), path=(x[1]||"").trim();
     var num=parseFloat(size)||0;
     var isG=/G/.test(size);
     var mb=isG?num*1024:num;
     var pct=total>0?Math.min(100,Math.round(mb/total*100)):0;
     return '<div style="margin-bottom:12px"><div class="row" style="border:0;padding:4px 0"><span class="k">'+esc(path.split("/").pop())+'</span><span class="v">'+esc(size)+'</span></div>'
       +'<div class="bar '+barCls(pct)+'"><i style="width:'+pct+'%"></i></div>'
       +'<div class="tip">'+esc(path)+'</div></div>';
   }).join('')
   +'</div>';
}
function cronHTML(c){
  return '<h2>计划任务</h2><div class="card">'+(c.length?c.map(function(x){return '<div class="row"><span class="v dim">'+esc(x)+'</span></div>'}).join(''):'<div class="dim">暂无计划任务</div>')+'</div>'
   +'<h2>新建计划任务</h2><div class="card"><input id="crn" placeholder="cron 表达式，如 */5 * * * *"><div style="margin-top:8px"><input id="crc" placeholder="命令，如 /home/user/.dsh_pend/bin/backup.sh"></div><div style="margin-top:9px"><button onclick="addCron()">添加</button></div></div><pre id="crout" class="hide"></pre>';
}
async function addCron(){var e=document.getElementById('crn').value.trim(),c=document.getElementById('crc').value.trim();if(!e||!c)return;var r=await api('/api/panel/cron_add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expr:e,cmd:c})});var el=document.getElementById('crout');el.classList.remove('hide');el.textContent=JSON.stringify(r);load()}
function backupHTML(){
  return '<h2>数据备份</h2><div class="card"><div class="tip">备份持久卷数据到 tar.gz（含数据库 dump、网站文件、配置）</div><div style="margin-top:10px"><button onclick="doBackup()">立即备份</button><button class="sec sm" onclick="load()">刷新</button></div></div><pre id="bkout" class="hide"></pre>';
}
async function doBackup(){var el=document.getElementById('bkout');el.classList.remove('hide');el.textContent='备份中…';var r=await api('/api/panel/backup',{method:'POST'});el.textContent=JSON.stringify(r,null,2)}
function ftpHTML(){
  return '<h2>FTP / SFTP 账户</h2><div class="card"><div class="tip">沙箱内可使用 sftp（22 端口）访问持久卷目录</div>'
   +'<div class="row"><span class="k">SFTP 地址</span><span class="v">沙箱内 127.0.0.1:22</span></div>'
   +'<div class="row"><span class="k">根目录</span><span class="v">/home/user/.dsh_pend</span></div></div>'
   +'<h2>说明</h2><div class="card dim" style="font-size:12.5px">FTP 需额外端口，当前通过 frp 仅暴露 80；如需 FTP 请在面板「容器应用」中启动 ftp server 并加隧道。</div>';
}
function termHTML(){
  return '<h2>终端（沙箱内执行）</h2><div class="card"><textarea id="cmd" rows="3" placeholder="输入命令，如 df -h"></textarea><div style="margin-top:9px;display:flex;gap:8px"><button id="cmdRun">执行</button><button class="sec" id="cmdClear">清屏</button></div></div><pre id="cout2">就绪</pre>';
}
function bindTerm(){
  var r=document.getElementById('cmdRun'), c=document.getElementById('cmdClear');
  if(r) r.onclick=runCmd;
  if(c) c.onclick=function(){document.getElementById('cout2').textContent=''};
}
async function runCmd(){var c=document.getElementById('cmd').value;if(!c.trim())return;var el=document.getElementById('cout2');el.textContent='执行中…';try{var r=await api('/api/panel/sh',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cmd:c})});el.textContent='$ '+c+'\n'+(r.out||'')+'\n[rc='+r.rc+']'}catch(e){el.textContent='失败: '+e.message}}
// ===== 实时更新（3 秒轮询 + 差值动画，无需刷新）=====
var liveTimer=null;
function startLive(){
  if(liveTimer)clearInterval(liveTimer);
  liveTimer=setInterval(async function(){
    try{
      if(cur==='overview'){
        var o=await api('/api/panel/overview');
        var mp=o.mem_total_mb?Math.round(o.mem_used_mb/o.mem_total_mb*100):0;
        var dp=parseFloat(o.disk_pct)||0;
        var set=function(id,val){var e=document.getElementById(id);if(e)e.textContent=val};
        set('kMem',o.mem_used_mb);
        set('kLoad','负载 '+o.load.split(' ')[0]);
        set('kProc',o.procs+' 进程');
        set('kUp',fmtU(o.uptime_sec));
        set('memTxt',o.mem_used_mb+'M / '+o.mem_total_mb+'M');
        set('diskTxt',o.disk_used+' / '+o.disk_total);
        set('hLoad',o.load);
        set('ovTime',new Date().toLocaleTimeString());
        var mb=document.getElementById('memBar');
        if(mb){mb.style.width=mp+'%';mb.parentNode.className='bar '+barCls(mp)}
        var db=document.getElementById('diskBar');
        if(db){db.style.width=dp+'%';db.parentNode.className='bar '+barCls(dp)}
        setLive(true);
      } else if(cur==='health'){
        var h=await api('/api/panel/services');
        var box=document.getElementById('hBox');
        if(box)box.innerHTML=h.map(function(x){return '<div class="row"><span class="k">'+esc(x.name)+'</span><span class="pill '+(x.ok?'ok':'err')+'">'+(x.ok?'正常':'异常')+'</span></div>'}).join('');
        setLive(true);
      } else if(cur==='procs'){
        var p=await api('/api/panel/procs');
        document.getElementById('view').innerHTML=procsHTML(p);
        setLive(true);
      } else { setLive(true); }
    }catch(e){setLive(false)}
  },3000);
}
async function boot(){
  renderNav();
  document.getElementById('view').innerHTML='<div class="card dim">连接中…</div>';
  try{var p=await api('/api/panel/ping');document.getElementById('hostSm').textContent=(p.host||'').replace(/^vefaas-/,'').split('-')[0]||'沙箱'}catch(e){}
  try{ await load(); }catch(e){ document.getElementById('view').innerHTML='<div class="card err">加载失败: '+esc(e.message)+'<br><br><button class="sec sm" onclick="location.reload(true)">强制刷新</button></div>'; }
  startLive();
}
window.addEventListener('error',function(ev){var v=document.getElementById('view');if(v&&v.innerHTML.indexOf('加载中')>=0){v.innerHTML='<div class="card err">JS 错误: '+esc(ev.message)+'<br><br><button class="sec sm" onclick="location.reload(true)">强制刷新</button></div>'}});
boot();
</script></body></html>"""


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
<div><div class="sw"><span>小任务保活</span><span class="green" id="keepGapTxt">每 60–90 秒一次（维持沙箱活跃）</span></div>
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
            elif p.path=="/api/sbx":
                c = ""
                if g("cmd64"):
                    try: c = base64.b64decode(g("cmd64")).decode()
                    except Exception: pass
                elif g("cmd"): c = g("cmd")
                self._send(sbx_sh(c, int(g("t","120"))))
            elif p.path=="/api/sbx/bg":
                try: c = base64.b64decode(g("cmd64")).decode()
                except Exception: c = ""
                self._send(sbx_bg(g("name","task"), c))
            elif p.path=="/panel/go":
                e = panel_entrance()
                self.send_response(302)
                self.send_header("Location", "/panel" + e)
                self.send_header("Cache-Control","no-store")
                self.end_headers()
            elif p.path=="/panel":
                b=PANEL_HTML.encode();self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8")
                self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
            elif p.path.startswith("/api/panel/"):
                sub = p.path[len("/api/panel/"):]
                def _body():
                    n = int(self.headers.get("Content-Length", 0))
                    return json.loads(self.rfile.read(n).decode("utf-8","ignore") if n else "{}")
                GET_MAP = {
                    "ping": "/api/ping", "overview": "/api/overview", "services": "/api/services",
                    "sites": "/api/sitelist", "sitelist": "/api/sitelist",
                    "databases": "/api/databases", "procs": "/api/procs",
                    "containers": "/api/containers", "cron": "/api/cron", "nginx_test": "/api/nginx_test",
                    "phpinfo": "/api/phpinfo", "disk": "/api/disk",
                }
                POST_MAP = {
                    "site_create": "/api/site_create", "site_add_domain": "/api/site_add_domain",
                    "site_ssl": "/api/site_ssl", "site_proxy": "/api/site_proxy",
                    "site_delete": "/api/site_delete", "nginx_reload": "/api/nginx_reload",
                    "cron_add": "/api/cron_add", "backup": "/api/backup",
                    "run_container": "/api/run_container",
                }
                if sub == "sessions":
                    try:
                        import conv_api as _CA
                        import accounts_db as _DB
                        lst = _CA.list_conv_with_health(30)
                        accs = _DB.list_accounts()
                        keep = accs[0].get("keep_conv_id") if accs else None
                        for x in lst:
                            x["keep"] = (str(x.get("conv_id")) == str(keep))
                        self._send(lst)
                    except Exception as e:
                        self._send({"error": "sessions: " + str(e)[:150]})
                elif sub in GET_MAP:
                    self._send(agent_get(GET_MAP[sub]))
                elif sub == "site_log":
                    self._send(agent_get("/api/site_log?name=" + urllib.parse.quote(g("name","")) + "&n=" + g("n","50")))
                elif sub == "tables":
                    self._send(agent_get("/api/tables?db=" + urllib.parse.quote(g("db",""))))
                elif sub == "dbquery":
                    self._send(agent_get("/api/dbquery?q=" + urllib.parse.quote(g("q",""))))
                elif sub == "ls":
                    self._send(agent_get("/api/ls?p=" + urllib.parse.quote(g("p",""))))
                elif sub == "read":
                    self._send(agent_get("/api/read?p=" + urllib.parse.quote(g("p",""))))
                elif sub in POST_MAP:
                    self._send(agent_post(POST_MAP[sub], _body()))
                elif sub == "sh":
                    self._send(agent_post("/api/sh", _body()))
                else:
                    self._send({"error": "unknown: " + sub})
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