#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chat_page.py — 仿豆包独立对话页（带返回、手机适配）"""

HTML = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>会话</title>
<style>
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;background:#0d1117;color:#e6edf3;font:15px/1.7 -apple-system,system-ui,sans-serif;height:100vh;display:flex;flex-direction:column}
header{display:flex;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid #30363d;background:#161b22;flex-shrink:0}
.back{background:none;border:0;color:#79c0ff;font-size:26px;padding:0 6px;cursor:pointer;line-height:1}
.title{flex:1;min-width:0;font-weight:600;font-size:15px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pill{font-size:11px;padding:2px 8px;border-radius:9px;white-space:nowrap}
.pill.live{background:#12341d;color:#3fb950}.pill.dead{background:#3a1418;color:#f85149}.pill.keep{background:#1b3a24;color:#7ee787}
#chat{flex:1;overflow-y:auto;padding:14px;scroll-behavior:smooth}
.m{max-width:88%;margin:10px 0;padding:9px 13px;border-radius:12px;white-space:pre-wrap;word-break:break-word;font-size:14px}
.m.bot{background:#161b22;border:1px solid #30363d;border-top-left-radius:3px;margin-right:auto}
.m.me{background:#1f6feb;color:#fff;border-top-right-radius:3px;margin-left:auto}
.m .who{font-size:11px;opacity:.6;margin-bottom:3px}
.bar{display:flex;gap:8px;padding:10px 12px;border-top:1px solid #30363d;background:#161b22;flex-shrink:0;align-items:center}
.bar input{flex:1;min-width:0;background:#0d1117;border:1px solid #30363d;color:#e6edf3;padding:10px 13px;border-radius:20px;font-size:15px;outline:none}
.bar button{background:#238636;border:0;color:#fff;padding:9px 16px;border-radius:20px;font-size:14px;white-space:nowrap}
.tools{display:flex;gap:6px;padding:6px 12px;background:#161b22;flex-wrap:wrap;border-top:1px solid #21262d}
.tools button{background:#21262d;border:1px solid #30363d;color:#c9d1d9;padding:5px 11px;border-radius:14px;font-size:12px}
.tip{text-align:center;color:#8b949e;font-size:12px;padding:4px}
#sending{display:none;text-align:center;color:#8b949e;font-size:12px;padding:3px}
@media(max-width:600px){.m{max-width:94%}.tools button{flex:1;text-align:center}.bar button{padding:9px 12px}}
</style></head><body>
<header><button class="back" onclick="goBack()">‹</button>
<div class="title" id="title">会话</div><span id="badges"></span></header>
<div id="chat"><div class="tip">加载中…</div></div>
<div id="sending">豆包正在回复…</div>
<div class="tools">
<button onclick="act('alive')">标记存活</button><button onclick="act('dead')">标记死亡</button>
<button onclick="renameIt()">重命名</button><button onclick="setKeep()">设为保活</button>
<button onclick="load()">刷新</button></div>
<div class="bar"><input id="inp" placeholder="发消息…" onkeydown="if(event.key==='Enter')send()"><button onclick="send()">发送</button></div>
<script>
const qs=new URLSearchParams(location.search);const cid=qs.get('cid')||'';
function goBack(){if(history.length>1)history.back();else location.href='/'}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
async function api(p){const r=await fetch(p);return r.json()}
async function load(){
  if(!cid){document.getElementById('chat').innerHTML='<div class="tip">无会话ID</div>';return}
  const [msgs,st]=await Promise.all([api('/api/conv/messages?cid='+encodeURIComponent(cid)),api('/api/conv/status?cid='+encodeURIComponent(cid))]);
  document.getElementById('title').innerText=st.name||cid;
  document.getElementById('badges').innerHTML=(st.keep?'<span class="pill keep">保活</span> ':'')+'<span class="pill '+(st.alive?'live':'dead')+'">'+(st.alive?'存活':'死亡')+'</span>';
  const box=document.getElementById('chat');
  box.innerHTML=msgs.length?msgs.slice().reverse().map(m=>'<div class="m '+(m.me?'me':'bot')+'"><div class="who">'+(m.me?'我':'豆包')+'</div>'+esc(m.text)+'</div>').join(''):'<div class="tip">暂无消息</div>';
  box.scrollTop=box.scrollHeight;
}
async function send(){
  const t=document.getElementById('inp').value.trim();if(!t)return;
  const box=document.getElementById('chat');
  box.insertAdjacentHTML('beforeend','<div class="m me"><div class="who">我</div>'+esc(t)+'</div>');
  document.getElementById('inp').value='';document.getElementById('sending').style.display='block';box.scrollTop=box.scrollHeight;
  try{
    const r=await fetch('/api/conv/send?cid='+encodeURIComponent(cid)+'&text='+encodeURIComponent(t));const d=await r.json();
    document.getElementById('sending').style.display='none';
    if(d.reply)box.insertAdjacentHTML('beforeend','<div class="m bot"><div class="who">豆包</div>'+esc(d.reply)+'</div>');
    if(d.death)box.insertAdjacentHTML('beforeend','<div class="tip" style="color:#f85149">☠️ 检测到拒绝/高风险，会话已标记死亡</div>');
  }catch(e){document.getElementById('sending').style.display='none'}
  box.scrollTop=box.scrollHeight;setTimeout(load,2500);
}
async function act(a){await api('/api/conv/'+a+'?cid='+encodeURIComponent(cid));load()}
async function renameIt(){const n=prompt('新会话名',document.getElementById('title').innerText);if(n){await api('/api/conv/rename?cid='+encodeURIComponent(cid)+'&name='+encodeURIComponent(n));load()}}
async function setKeep(){const st=await api('/api/status');if(!st.account)return;await api('/api/keep/set?uid='+encodeURIComponent(st.account.uid)+'&cid='+encodeURIComponent(cid)+'&name='+encodeURIComponent(document.getElementById('title').innerText));load()}
load();setInterval(load,15000);
</script></body></html>"""
