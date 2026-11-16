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
    out = page_eval(js, 100) or ""
    # 只在明确收到 STREAM_ERROR 且没有 SSE_ACK 时才视为失败；
    # SSE_ACK + 后续内容 = 真落库（瞬时 710022004 不代表本次失败）
    if "STREAM_ERROR" in out and "SSE_ACK" not in out:
        return ""
    return out

# ---- 重命名（已抓包验证）----
def rename(conv_id, name):
    """重命名：先确保 CDP 页面在已登录的会话页（/chat 新对话页签名环境会报用户不合法）"""
    # 重新注入完整 cookie（测试导航 /chat 会冲掉浏览器登录态）
    try:
        subprocess.run(["python3","/root/inject_ck.py","/root/ck_live2.txt"],capture_output=True,text=True,timeout=40)
        time.sleep(4)
    except Exception: pass
    try:
        w = websocket.create_connection(page_ws(), timeout=30)
        w.send(json.dumps({"id":8,"method":"Page.navigate","params":{"url":"https://www.doubao.com/chat/38453755360368898"}}))
        time.sleep(1); w.close(); time.sleep(5)
    except Exception: pass
    return page_post_json("/alice/conversation/update", {"conversation_id":conv_id,"name":name})

# ---- 新建会话 ----
def create_conv(name=""):
    # /im/conversation/create 或 need_create_conversation=true 发一条消息
    out = send_full("", "__NEW_CONV__")  # 空 id -> 服务端新建；实际由调用方传特殊值处理
    return out

def create_conv_by_send(name):
    """新建会话：按抓到的真实首条消息 body 构造（local_conversation_id + conversation_init_option 等）
    发成功后从 SSE 取 conversation_id，并立即按配置重命名。
    """
    js = r"""
(async()=>{
  const ck=Object.fromEntries(document.cookie.split('; ').map(s=>{const i=s.indexOf('=');return[s.slice(0,i),s.slice(i+1)];}));
  const tea=JSON.parse(localStorage.getItem('__tea_cache_tokens_497858')||'{}');
  const sam=JSON.parse(localStorage.getItem('samantha_web_web_id')||'{}');
  const device_id=sam.web_id||'7707456447802197504', web_id=tea.web_id||device_id;
  const p=new URLSearchParams({aid:'497858',device_id:device_id,device_platform:'web',doubao_device_platform:'web',doubao_pc_version:'3.45.7',fp:ck['s_v_web_id']||'',language:'zh',pc_version:'3.45.7',pkg_type:'release_version',real_aid:'497858',region:'CN',samantha_web:'1',sys_region:'CN',tea_uuid:web_id,tz_name:'Asia/Shanghai','use-olympus-account':'1',version_code:'20800',web_id:web_id,web_platform:'browser',web_tab_id:crypto.randomUUID(),msToken:ck['msToken']||''});
  const localId='local_'+Date.now()+Math.floor(Math.random()*1000);
  const mid=crypto.randomUUID(), uid=crypto.randomUUID(), bid=crypto.randomUUID();
  const agentTask={runtime_type:1,folder_name:'',device_name:'',workspace:'',local_app_id:'',local_device_id:''};
  const body={client_meta:{local_conversation_id:localId,conversation_id:'',bot_id:'7338286299411103781',last_section_id:'',last_message_index:null,local_permissions:[{permission_name:'ACCESS_COARSE_LOCATION',status:3},{permission_name:'ACCESS_FINE_LOCATION',status:3},{permission_name:'ACCESS_BACKGROUND_LOCATION',status:3}]},messages:[{local_message_id:mid,content_block:[{block_type:10000,content:{text_block:{text:'新会话初始化',icon_url:'',icon_url_dark:'',summary:''},pc_event_block:''},block_id:bid,parent_id:'',meta_info:[],extra_info:{},append_fields:[]}],message_status:0}],option:{send_message_scene:'',create_time_ms:Date.now(),collect_id:'',is_audio:false,answer_with_suggest:false,agent_mode:1,tts_switch:false,need_deep_think:9,click_clear_context:false,from_suggest:false,is_regen:false,is_replace:false,is_from_click_option:false,is_from_click_softlink:false,disable_sse_cache:false,select_text_action:'',is_select_text:false,resend_for_regen:false,scene_type:0,unique_key:uid,start_seq:0,need_create_conversation:true,conversation_init_option:{project_id:'',need_ack_conversation:true},conversation_init_ext:{agent_task_param:JSON.stringify(agentTask),model_item_key:'9',reasoning_effort:'3',mode_id:'3'},regen_query_id:[],edit_query_id:[],regen_instruction:'',no_replace_for_regen:false,message_from:0,shared_app_name:'',shared_app_id:'',sse_recv_event_options:{support_chunk_delta:true},support_lazy_fetch_stream:true,is_ai_playground:false,is_old_user:true,general_task_param:{action:0,thread_local_message_id:[mid],project_id:'',runtime_type:1,agent_task_param:agentTask,server_do_compare:true},queue_client_state:{queue_enabled:true,queue_is_empty:true,queue_submit_mode:2},recovery_option:{is_recovery:false,req_create_time_sec:Math.floor(Date.now()/1000),append_sse_event_scene:0},message_storage_type:0,related_deleted_message_ids:{},connector_info_list:[],model_config:{model_item_key:'9',model_extra_params:{total_window_size:'256000'},reasoning_effort:3},aggregate_params:{mention_skill_list:'[]',mention_plugin_list:'[]',mention_ext:'[{}]',conversation_mode:'2',mode_id:'3',model_item_key:'9',agent_mode:'1',reasoning_effort:'3',provider_id:''},conversation_mode:2},user_context:[],ext:{general_task_param:JSON.stringify({action:0,thread_local_message_id:[mid],project_id:'',runtime_type:1,agent_task_param:agentTask,server_do_compare:true}),use_deep_think:'9',agent_mode:'1',conversation_init_option:JSON.stringify({project_id:'',need_ack_conversation:true}),sub_conv_firstmet_type:'1',collection_id:'',is_finish:'1',commerce_credit_config_enable:'0'}};
  const r=await fetch('/chat/completion?'+p.toString(),{method:'POST',credentials:'include',headers:{'Content-Type':'application/json','Agw-Js-Conv':'str, str','Accept':'text/event-stream'},body:JSON.stringify(body)});
  return await r.text();
})()
"""
    # 真人路径：先切到新对话页 /chat，再发首条消息（否则会进无状态通道）
    w = websocket.create_connection(page_ws(), timeout=30)
    w.send(json.dumps({"id": 9, "method": "Page.navigate", "params": {"url": "https://www.doubao.com/chat"}}))
    time.sleep(1)
    w.close()
    time.sleep(7)
    old_ids = {x["id"] for x in sessions()}
    sse = page_eval(js, 100) or ""
    # 新会话由首条消息创建；SSE 里的数字 ID 不是会话 ID，重新拉列表找新增的
    cid = ""
    for _ in range(6):
        time.sleep(3)
        for x in sessions():
            if x["id"] not in old_ids and (x["name"] in ("新会话初始化", "(未命名)", "") or x["id"] not in old_ids):
                cid = x["id"]; break
        if cid: break
    if cid and name:
        rename(cid, name)
    return {"conversation_id":cid, "name":name, "sse_head":sse[:160],
            "need_manual": not bool(cid),
            "hint":"" if cid else "新建后未从会话列表找到新会话，请在豆包页面发首条消息创建；管理台自动读取后可重命名/设保活"}

def create_conv_by_ui(name):
    """真人路径新建会话：/chat → insertText → 动态找发送按钮 → 点击 → 列表定位 → 重命名"""
    w = websocket.create_connection(page_ws(), timeout=60)
    w.send(json.dumps({"id":1,"method":"Page.navigate","params":{"url":"https://www.doubao.com/chat"}}))
    time.sleep(8)
    old_ids = {x["id"] for x in sessions()}
    def c(i, method, params=None, wait=20):
        w.send(json.dumps({"id":i,"method":method,"params":params or {}}))
        end=time.time()+wait
        while time.time()<end:
            r=json.loads(w.recv())
            if r.get("id")==i: return r
    # 聚焦 textarea 并用 insertText（比逐字 char 可靠）
    # React 受控 textarea：用 native setter + input 事件注入文字
    c(2,"Runtime.evaluate",{"expression":"""
(()=>{const t=document.querySelector('[data-testid=chat_input_input]');if(!t)return 'NO';
const s=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
s.call(t,'新会话初始化');t.dispatchEvent(new Event('input',{bubbles:true}));t.focus();return t.value})()
""","returnByValue":True})
    time.sleep(1)
    # 动态查发送按钮坐标
    r=c(4,"Runtime.evaluate",{"expression":"""
(()=>{const e=document.querySelector('[data-testid=chat_input_send_button]');if(!e)return '';const b=e.getBoundingClientRect();return Math.round(b.x+b.width/2)+','+Math.round(b.y+b.height/2)})()
""","returnByValue":True})
    pos=r.get("result",{}).get("result",{}).get("value") or ""
    if not pos:
        w.close(); return {"conversation_id":"","name":name,"need_manual":True,"hint":"发送按钮未出现（输入未生效）"}
    x,y=map(int,pos.split(","))
    c(5,"Input.dispatchMouseEvent",{"type":"mousePressed","x":x,"y":y,"button":"left","clickCount":1})
    c(6,"Input.dispatchMouseEvent",{"type":"mouseReleased","x":x,"y":y,"button":"left","clickCount":1})
    w.close()
    cid=""
    for _ in range(6):
        time.sleep(3)
        for item in sessions():
            if item["id"] not in old_ids:
                cid=item["id"]; break
        if cid: break
    if cid and name: rename(cid, name)
    return {"conversation_id":cid,"name":name,
            "need_manual": not bool(cid),
            "hint":"" if cid else "UI 新建后未从列表找到新会话"}

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


# ---- 新接口发送（/samantha/chat/completion，已验证可用）----
def send_samantha(conv_id, text, create=False):
    """通过 /samantha/chat/completion 发送。conv_id='0' 或 create=True 时新建会话。
    返回 SSE 全文。成功特征：包含 message_id / event_type。
    """
    js = r'''
(async()=>{
 try{
  const ck=Object.fromEntries(document.cookie.split('; ').map(s=>{const i=s.indexOf('=');return[s.slice(0,i),s.slice(i+1)];}));
  const params={aid:'497858',device_platform:'web',language:'zh',pc_version:'2.41.0',
    pkg_type:'release_version',real_aid:'497858',region:'CN',samantha_web:'1',sys_region:'CN',
    'use-olympus-account':'1',version_code:'20800',
    device_id:ck['s_v_web_id']||'', fp:ck['s_v_web_id']||'',
    web_tab_id:crypto.randomUUID(), msToken:ck['msToken']||''};
  const sorted=Object.keys(params).sort().reduce((o,k)=>{o[k]=params[k];return o},{});
  const qs=new URLSearchParams(sorted).toString();
  let bogus='';
  try{ const s=await window.bdms.frontierSign(qs); bogus=s&&(s['X-Bogus']||s['a_bogus'])||''; }catch(e){}
  const url='/samantha/chat/completion?'+qs+(bogus?'&X-Bogus='+bogus:'');
  const payload={messages:[{content:JSON.stringify({text:%TEXT%}),content_type:2001,attachments:[],references:[]}],
    completion_option:{is_regen:false,with_suggest:true,need_create_conversation:%CREATE%,launch_stage:1,
      is_replace:false,is_delete:false,message_from:0,action_bar_skill_id:0,use_deep_think:false,
      use_auto_cot:true,resend_for_regen:false,enable_commerce_credit:false,event_id:'0'},
    evaluate_option:{web_ab_params:''}, conversation_id:%CID%,
    local_conversation_id:'local_'+crypto.randomUUID().replace(/-/g,''),
    local_message_id:crypto.randomUUID()};
  const r=await fetch(url,{method:'POST',credentials:'include',headers:{
    'Accept':'*/*','Content-Type':'application/json','Origin':'https://www.doubao.com',
    'Referer':'https://www.doubao.com/chat/','agw-js-conv':'str, str'},
    body:JSON.stringify(payload)});
  return await r.text();
 }catch(e){return 'EXEC_ERR '+e.message}
})()
'''.replace("%TEXT%", json.dumps(text, ensure_ascii=False)) \
   .replace("%CID%", json.dumps(str(conv_id))) \
   .replace("%CREATE%", "true" if (create or str(conv_id) == "0") else "false")
    return page_eval(js, 120) or ""

def send_and_get_ids(conv_id, text, create=False, auto_save=True):
    """发送并返回 (ok, message_id, conversation_id, raw)。
    create=True 或 conv_id='0' 时新建会话，并自动把新会话存入 DB 作为保活会话。
    """
    raw = send_samantha(conv_id, text, create=create)
    if not raw:
        return False, None, None, ""
    if "710022002" in raw or "710022004" in raw:
        return False, None, None, raw
    import re as _re
    mid = (_re.search(r'"message_id":"(\d+)"', raw) or [None, None])[1]
    conv = (_re.search(r'"conversation_id":"(\d+)"', raw) or [None, None])[1]
    ok = bool(mid or '"event_type":2002' in raw)

    # 自动保存会话（新建或首次发送）
    if ok and conv and auto_save:
        try:
            import accounts_db as _DB
            accs = _DB.list_accounts()
            uid = accs[0]["uid"] if accs else None
            if uid:
                acc = _DB.get_account(uid)
                if not acc or not acc.get("keep_conv_id"):
                    name = "老王（A）"
                    _DB.set_keep_conv(uid, conv, name)
                    _DB.upsert_conv(uid, conv, name=name, alive=1)
                else:
                    _DB.upsert_conv(uid, conv, alive=1)
        except Exception:
            pass
    return ok, mid, conv, raw
