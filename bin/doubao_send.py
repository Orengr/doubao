#!/usr/bin/env python3
# doubao_send.py — 经真浏览器页面环境调用 /chat/completion 发送消息
# 用法: python3 doubao_send.py <conversation_id> <text>
# 依赖: 服务器 Xvfb :99 + 非headless chromium CDP 9222 + ck_live2.txt 已注入
import json, urllib.request, time, websocket, sys, uuid

CONV = sys.argv[1] if len(sys.argv) > 1 else '38453425674259202'
TEXT = sys.argv[2] if len(sys.argv) > 2 else 'ka_pure 保活任务'

tabs = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json/list', timeout=10).read())
tab = next(t for t in tabs if 'doubao.com/chat' in (t.get('url') or ''))
ws = websocket.create_connection(tab['webSocketDebuggerUrl'], timeout=90)

js = '''
(async () => {
  const ck = Object.fromEntries(document.cookie.split('; ').map(s => { const i=s.indexOf('='); return [s.slice(0,i), s.slice(i+1)]; }));
  const tea = JSON.parse(localStorage.getItem('__tea_cache_tokens_497858') || '{}');
  const sam = JSON.parse(localStorage.getItem('samantha_web_web_id') || '{}');
  const device_id = sam.web_id || '7707456447802197504';
  const web_id = tea.web_id || device_id;
  const p = new URLSearchParams({
    aid:'497858', device_id:device_id, device_platform:'web', doubao_device_platform:'web',
    doubao_pc_version:'3.45.7', fp:ck['s_v_web_id']||'', language:'zh', pc_version:'3.45.7',
    pkg_type:'release_version', real_aid:'497858', region:'CN', samantha_web:'1',
    sys_region:'CN', tea_uuid:web_id, tz_name:'Asia/Shanghai', 'use-olympus-account':'1',
    version_code:'20800', web_id:web_id, web_platform:'browser',
    web_tab_id:crypto.randomUUID(), msToken:ck['msToken']||''
  });
  const body = {
    client_meta:{conversation_id:%CONV%, bot_id:'7338286299411103781', last_section_id:'', last_message_index:0, local_permissions:[]},
    messages:[{local_message_id:crypto.randomUUID(), content_block:[{block_type:10000,
      content:{text_block:{text:%TEXT%, icon_url:'', icon_url_dark:'', summary:''}}, pc_event_block:'',
      block_id:crypto.randomUUID(), parent_id:'', meta_info:[], extra_info:{}, append_fields:[]}], message_status:0}],
    option:{send_message_scene:'', create_time_ms:Date.now(), collect_id:'', is_audio:false,
      answer_with_suggest:false, agent_mode:1, tts_switch:false, need_deep_think:9,
      click_clear_context:false, from_suggest:false, is_regen:false, is_replace:false,
      is_from_click_option:false, is_from_click_softlink:false, disable_sse_cache:false,
      select_text_action:'', is_select_text:false, resend_for_regen:false, scene_type:0,
      unique_key:crypto.randomUUID(), start_seq:0, need_create_conversation:false,
      regen_query_id:[], edit_query_id:[], regen_instruction:'', no_replace_for_regen:false,
      message_from:0, shared_app_name:'', shared_app_id:'',
      sse_recv_event_options:{support_chunk_delta:true}, support_lazy_fetch_stream:true,
      is_ai_playground:false, is_old_user:true,
      general_task_param:{action:0, thread_local_message_id:[crypto.randomUUID()], project_id:'', runtime_type:1,
        agent_task_param:{runtime_type:1, folder_name:'', device_name:'', workspace:'', local_app_id:'', local_device_id:''}, server_do_compare:true},
      queue_client_state:{queue_enabled:true, queue_is_empty:true, queue_submit_mode:2},
      recovery_option:{is_recovery:false, req_create_time_sec:Math.floor(Date.now()/1000), append_sse_event_scene:0}}
  };
  const r = await fetch('/chat/completion?' + p.toString(), {
    method:'POST', credentials:'include',
    headers:{'Content-Type':'application/json','Agw-Js-Conv':'str, str','Accept':'text/event-stream'},
    body: JSON.stringify(body)
  });
  const t = await r.text();
  return JSON.stringify({status:r.status, head:t.slice(0,200)});
})()
'''.replace('%CONV%', json.dumps(CONV)).replace('%TEXT%', json.dumps(TEXT));

ws.send(json.dumps({'id':1,'method':'Runtime.evaluate','params':{'expression':js,'awaitPromise':True,'returnByValue':True}}))
deadline = time.time() + 80
out = None
while time.time() < deadline:
    try:
        r = json.loads(ws.recv())
        if r.get('id') == 1:
            out = r.get('result',{}).get('result',{}).get('value')
            break
    except Exception: break
ws.close()
print(out or 'NO_RESPONSE')
