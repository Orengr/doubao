#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""conv_api.py — 会话操作：列表/消息/发送/重命名/新建/死亡检测
全部经页面 CDP 环境调用（真浏览器签名+设备身份），接口路径已抓包验证。
"""
import json, urllib.request, websocket, time, subprocess, re, sys

CDP = "http://127.0.0.1:9222"
CK_FILE = "/root/ck_live2.txt"
def ck_header():
    import os
    f = CK_FILE
    try:
        a = json.load(open("/root/active_account.json"))
        if a.get("cookie_file") and os.path.exists(a["cookie_file"]): f = a["cookie_file"]
    except Exception: pass
    return "; ".join(l.strip() for l in open(f) if "=" in l)
UA = "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"

def page_ws():
    tabs = json.loads(urllib.request.urlopen(CDP+"/json/list", timeout=10).read())
    t = next((x for x in tabs if x["type"] == "page"), None)
    if not t: raise RuntimeError("no CDP page")
    return t["webSocketDebuggerUrl"]

def page_eval(js, timeout=60):
    w = websocket.create_connection(page_ws(), timeout=timeout)
    w.send(json.dumps({"id":1,"method":"Runtime.evaluate","params":{"expression":js,"awaitPromise":True,"returnByValue":True}}))
    end=time.time()+timeout; out=None
    while time.time()<end:
        try:
            r=json.loads(w.recv())
            if r.get("id")==1:
                out=r.get("result",{}).get("result",{}).get("value"); break
        except Exception: break
    w.close(); return out

def page_post(path, body):
    """页面上下文 POST（同源 cookie + bdms 签名环境）"""
    js = """
(async()=>{
  const r=await fetch(%s,{method:'POST',credentials:'include',
    headers:{'Content-Type':'application/json','Agw-Js-Conv':'str, str','Accept':'text/event-stream'},
    body:%s});
  return await r.text();
})()
""" % (json.dumps(path), json.dumps(json.dumps(body, separators=(",",":"))))
    return page_eval(js, 90) or ""

def page_post_json(path, body):
    js = """
(async()=>{
  const r=await fetch(%s,{method:'POST',credentials:'include',
    headers:{'Content-Type':'application/json','Agw-Js-Conv':'str'},
    body:%s});
  return await r.text();
})()
""" % (json.dumps(path+"?aid=497858"), json.dumps(json.dumps(body, separators=(",",":"))))
    return page_eval(js, 40) or ""

# ---- 读取（curl 直连，已验证）----
def _db_post(path, body):
    import subprocess as _sp
    url = "https://www.doubao.com/" + path + "?aid=497858&samantha_web=1"
    cmd = ["curl","-s","--max-time","20","-X","POST",url,
      "-H","Cookie: "+ck_header(),
      "-H","Content-Type: application/json; encoding=utf-8",
      "-H","agw-js-conv: str",
      "-H","User-Agent: "+UA,
      "-H","Referer: https://www.doubao.com/chat/",
      "--data-raw", json.dumps(body,separators=(",",":"))]
    return _sp.run(cmd,capture_output=True,text=True,timeout=25).stdout

def recent(limit=30):
    b={"cmd":3200,"uplink_body":{"pull_recent_conv_chain_uplink_body":{"conv_version":0,"limit":limit,"message_count_per_conv":1,"option":{"not_need_message":False,"need_complete_conversation":True,"need_coco_conversation":True,"need_coco_bot":True,"pc_pin_query_type":0},"api_version":1,"direction":3}},"sequence_id":"c1","channel":2,"version":"1"}
    try: return json.loads(_db_post("im/chain/recent_conv",b)).get("downlink_body",{}).get("pull_recent_conv_chain_downlink_body",{}).get("cells",[])
    except Exception: return []

def sessions():
    return [{"id":c.get("conversation",{}).get("conversation_id",""),
             "name":c.get("conversation",{}).get("name","") or "(未命名)"} for c in recent()]

def single(conv_id, limit=30):
    b={"cmd":3100,"uplink_body":{"pull_singe_chain_uplink_body":{"conversation_id":conv_id,"anchor_index":9007199254740991,"conversation_type":3,"direction":1,"limit":limit,"ext":{},"filter":{"index_list":[]},"evaluate_ab_params":"","evaluate_common_params":"","option":{"lazy_load_strategy":0}}},"sequence_id":"c2","channel":2,"version":"1"}
    try: return json.loads(_db_post("im/chain/single",b)).get("downlink_body",{}).get("pull_singe_chain_downlink_body",{}).get("messages",[])
    except Exception: return []

# ---- 发送（真 /chat/completion，返回 SSE 全文用于死亡检测）----
def send(conv_id, text):
    # 复用已验证的 doubao_send.py（页面环境，带完整设备身份+a_bogus）
    r=subprocess.run(["python3","/root/doubao_send.py",conv_id,text],capture_output=True,text=True,timeout=110)
    return r.stdout.strip()

def send_full(conv_id, text):
    """页面上下文直接发 /chat/completion，收集完整 SSE（用于读取豆包回复）"""
    js = r"""
(async()=>{
  const ck=Object.fromEntries(document.cookie.split('; ').map(s=>{const i=s.indexOf('=');return[s.slice(0,i),s.slice(i+1)];}));
  const tea=JSON.parse(localStorage.getItem('__tea_cache_tokens_497858')||'{}');
  const sam=JSON.parse(localStorage.getItem('samantha_web_web_id')||'{}');
  const device_id=sam.web_id||'7707456447802197504', web_id=tea.web_id||device_id;
  const p=new URLSearchParams({aid:'497858',device_id:device_id,device_platform:'web',doubao_device_platform:'web',doubao_pc_version:'3.45.7',fp:ck['s_v_web_id']||'',language:'zh',pc_version:'3.45.7',pkg_type:'release_version',real_aid:'497858',region:'CN',samantha_web:'1',sys_region:'CN',tea_uuid:web_id,tz_name:'Asia/Shanghai','use-olympus-account':'1',version_code:'20800',web_id:web_id,web_platform:'browser',web_tab_id:crypto.randomUUID(),msToken:ck['msToken']||''});
  const body={client_meta:{conversation_id:%CID%,bot_id:'7338286299411103781',last_section_id:'',last_message_index:0,local_permissions:[]},messages:[{local_message_id:crypto.randomUUID(),content_block:[{block_type:10000,content:{text_block:{text:%TEXT%,icon_url:'',icon_url_dark:'',summary:''}},pc_event_block:'',block_id:crypto.randomUUID(),parent_id:'',meta_info:[],extra_info:{},append_fields:[]}],message_status:0}],option:{send_message_scene:'',create_time_ms:Date.now(),collect_id:'',is_audio:false,answer_with_suggest:false,agent_mode:1,tts_switch:false,need_deep_think:9,click_clear_context:false,from_suggest:false,is_regen:false,is_replace:false,is_from_click_option:false,is_from_click_softlink:false,disable_sse_cache:false,select_text_action:'',is_select_text:false,resend_for_regen:false,scene_type:0,unique_key:crypto.randomUUID(),start_seq:0,need_create_conversation:false,regen_query_id:[],edit_query_id:[],regen_instruction:'',no_replace_for_regen:false,message_from:0,shared_app_name:'',shared_app_id:'',sse_recv_event_options:{support_chunk_delta:true},support_lazy_fetch_stream:true,is_ai_playground:false,is_old_user:true,general_task_param:{action:0,thread_local_message_id:[crypto.randomUUID()],project_id:'',runtime_type:1,agent_task_param:{runtime_type:1,folder_name:'',device_name:'',workspace:'',local_app_id:'',local_device_id:''},server_do_compare:true},queue_client_state:{queue_enabled:true,queue_is_empty:true,queue_submit_mode:2},recovery_option:{is_recovery:false,req_create_time_sec:Math.floor(Date.now()/1000),append_sse_event_scene:0}}};
  const r=await fetch('/chat/completion?'+p.toString(),{method:'POST',credentials:'include',headers:{'Content-Type':'application/json','Agw-Js-Conv':'str, str','Accept':'text/event-stream'},body:JSON.stringify(body)});
  return await r.text();
})()
""".replace("%CID%", json.dumps(conv_id)).replace("%TEXT%", json.dumps(text, ensure_ascii=False))
    return page_eval(js, 100) or ""

# ---- 重命名（已抓包验证）----
def rename(conv_id, name):
    return page_post_json("/alice/conversation/update", {"conversation_id":conv_id,"name":name})

# ---- 新建会话 ----
def create_conv(name=""):
    # /im/conversation/create 或 need_create_conversation=true 发一条消息
    out = send_full("", "__NEW_CONV__")  # 空 id -> 服务端新建；实际由调用方传特殊值处理
    return out

def create_conv_by_send(name):
    """新建会话：优先接口；接口不通则明确返回失败（前端提示用户手动新建）
    注：豆包新建会话由发首条消息触发，管理台会自动从 recent_conv 读到并可重命名。
    """
    return {"conversation_id":"", "name":name,
            "need_manual": True,
            "hint":"豆包新会话需在页面发首条消息创建；创建后管理台自动读取，点会话可重命名/设保活"}

# ---- 死亡检测 ----
def death_check(sse_text, keywords):
    """SSE 回复里出现拒绝/高危关键词 → 返回命中的词，否则 None"""
    if not sse_text: return None
    for kw in keywords.split("|"):
        if kw and kw in sse_text: return kw
    return None

def extract_reply(sse_text):
    """从 SSE 里抽取豆包回复文本（简单聚合 text 字段）"""
    texts = re.findall(r'"text":"([^"\\]{2,200})"', sse_text)
    out=[]
    for t in texts:
        try: t=json.loads('"'+t+'"')
        except Exception: pass
        if t and t not in out: out.append(t)
    return " ".join(out[:8])[:400]
