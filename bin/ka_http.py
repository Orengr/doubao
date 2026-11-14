#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ka_http.py — v3 纯 HTTP 保活引擎（无浏览器）

流程：
  1. cookie 活性检查（recent_conv 可调 = 有效）
  2. 隧道探测（17800/18090）
  3. 隧道断 → chat/completion 发恢复指令
  4. 正常时轮换轻量任务保活
  5. 熔断/冷却/错误码判定，710020702 → 触发扫码

依赖：标准库。低 CPU（<1%），1核512M 服务器友好。
"""
import os, json, time, uuid, copy, logging, threading, urllib.request

BASE = "https://www.doubao.com"
QS = "version_code=20800&language=zh&device_platform=web&aid=497858&real_aid=497858&pkg_type=release_version"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) HeadlessChrome/156.0.8078.4 Safari/537.36")
BOT_ID = "7338286299411103781"
CK = os.environ.get("CK_FILE", "/root/ck_full.txt")
STATE_F = os.environ.get("KA_STATE", "/root/ka_state.json")
CONF_F = os.environ.get("KA_CONF", "/root/keepconf.json")
CTL = os.environ.get("CTL_URL", "http://127.0.0.1:17800")
PANEL = os.environ.get("PANEL_URL", "http://127.0.0.1:18090")
LOG_F = os.environ.get("KA_LOG", "/root/keepalive.log")

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_F, encoding="utf-8"), logging.StreamHandler()])
log = logging.getLogger("ka_http")

TASK_TEMPLATES = [
    "在沙箱 /home/user/.dsh_pend/tasks/ 下创建一个商品报价表 CSV（商品名、单价、数量、总价），至少 8 行，文件名带时间戳 {ts}",
    "在沙箱 /home/user/.dsh_pend/tasks/ 下写一篇 200 字作文，主题随机，保存为 essay_{ts}.md 并告诉我路径",
    "用几行代码写一个简洁的网页 404 界面（带样式和返回按钮），保存到 /home/user/.dsh_pend/tasks/404_{ts}.html",
    "在沙箱统计 /home/user/.dsh_pend 下各子目录大小，从大到小列出前 10 名，记录到 tasks/du_{ts}.txt",
    "在沙箱生成一份系统信息报告（CPU 核数、内存、磁盘、运行时长），保存到 tasks/sysinfo_{ts}.txt",
    "在沙箱写一个 Python 计算器脚本（支持加减乘除），保存到 tasks/calc_{ts}.py 并运行一次验证",
    "在沙箱生成 10 条随机励志名言，保存为 JSON 到 tasks/quotes_{ts}.json",
    "在沙箱用 bash 把 /home/user/.dsh_pend/www 打包成 tar.gz 存到 tasks，并报告压缩包大小 {ts}",
]
WAKE_CMD = ("沙箱隧道断了，请执行 sh /home/user/.dsh_pend/bin/ensure.sh "
            "重新拉起所有服务，执行完把最后 10 行输出发我")

# ---------- 状态 ----------
def load_state():
    try: return json.load(open(STATE_F))
    except Exception:
        return {"fail_streak":0,"last_task":0,"last_wake":0,"task_idx":-1,"stopped":False}

def save_state(st):
    try: json.dump(st, open(STATE_F,"w"), ensure_ascii=False, indent=1)
    except Exception: pass

def get_target():
    try:
        c = json.load(open(CONF_F))
        t = (c.get("target") or "").strip()
        if t.isdigit(): return t
    except Exception: pass
    try: return open("/root/ka_target.txt").read().strip()
    except Exception: return ""

# ---------- cookie ----------
def cookie_header():
    try:
        return "; ".join(l.strip() for l in open(CK) if "=" in l)
    except Exception:
        return ""

def http_post(path, body_dict, referer="/chat/", timeout=30):
    hdr = cookie_header()
    if not hdr:
        return None, "no cookie"
    data = json.dumps(body_dict).encode()
    req = urllib.request.Request(BASE+path+"?"+QS, data=data, headers={
        "Cookie": hdr, "User-Agent": UA, "Referer": BASE+referer,
        "Content-Type": "application/json; encoding=utf-8"})
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.read().decode(errors="ignore"), ""
    except Exception as e:
        return None, str(e)[:100]

# ---------- 活性检查 ----------
def cookie_alive():
    uplink = {"pull_recent_conv_chain_uplink_body":{
        "conv_version":0,"limit":5,
        "filter":{"conversation_type":[],"project_filter":0,"device_filter":1},
        "message_count_per_conv":0,
        "option":{"not_need_message":True,"need_complete_conversation":True,
                  "need_coco_bot":True}}}
    body = {"cmd":3200,"uplink_body":uplink,
            "sequence_id":str(uuid.uuid4()),"channel":2,"version":"1"}
    t, err = http_post("/im/chain/recent_conv", body)
    if t is None: return False, err
    try:
        d = json.loads(t)
        sc = d.get("status_code")
        uid = d.get("downlink_body",{}).get("pull_recent_conv_chain_downlink_body",{}).get("user_id","")
        if sc == 0 and uid:
            return True, uid
        return False, f"status={sc}"
    except Exception as e:
        return False, str(e)[:80]

# ---------- 发送 ----------
def send_sse(conv_id, text, timeout=100):
    """返回 (ok, err)。ok=True 表示消息被受理"""
    tmpl_f = "/root/send_template.json"
    if os.path.exists(tmpl_f):
        base = json.load(open(tmpl_f))
    else:
        base = {"client_meta":{},"messages":[{}],"option":{},
                "user_context":[],"ext":{},"agent_mode":"2",
                "general_task_param":{"server_do_compare":True},
                "is_ai_playground":False,"from_suggest":False,
                "answer_with_suggest":False,"click_clear_context":False,
                "edit_query_id":"","disable_sse_cache":False,
                "append_sse_event_scene":"","connector_info_list":[],
                "extra_info":{}}
    b = copy.deepcopy(base)
    cm = b.setdefault("client_meta", {})
    cm["conversation_id"] = conv_id or ""
    cm["local_conversation_id"] = "local_" + str(uuid.uuid1())[:13]
    cm.setdefault("bot_id", BOT_ID)
    cm.setdefault("last_section_id","")
    cm.setdefault("last_message_index", None)
    cm.setdefault("local_permissions", [])
    msgs = b.setdefault("messages",[{}])
    m = msgs[0] = msgs[0] if msgs and isinstance(msgs[0], dict) else {}
    lm = str(uuid.uuid1())
    m["local_message_id"] = lm
    m["content_block"] = [{"block_type":10000,
        "content":{"text_block":{"text":text,"icon_url":"","icon_url_dark":"","summary":""},
                   "pc_event_block":""},
        "block_id":str(uuid.uuid4()),"parent_id":"","meta_info":[],
        "extra_info":{},"append_fields":[]}]
    m["message_status"] = 0
    op = b.setdefault("option",{})
    op["create_time_ms"] = int(time.time()*1000)
    req = urllib.request.Request(
        BASE+"/chat/completion?"+QS, data=json.dumps(b).encode(),
        headers={"Cookie":cookie_header(),"User-Agent":UA,
                 "Referer":BASE+"/chat/"+(conv_id or ""),
                 "Content-Type":"application/json; encoding=utf-8",
                 "Accept":"text/event-stream"})
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        buf = b""
        start = time.time()
        while time.time()-start < timeout:
            ch = r.read(2048)
            if not ch: break
            buf += ch
            if b"STREAM_ERROR" in buf:
                t = buf.decode(errors="ignore")
                i = t.find("STREAM_ERROR")
                seg = t[i:i+220]
                if "710020202" in seg:
                    return False, "invalid param(结构错误)"
                if "710020702" in seg:
                    return False, "session dead(cookie死/会话死)"
                return False, seg[:120]
            if len(buf) > 20000:
                break
        # 无 STREAM_ERROR：受理成功（心跳或正文）
        return True, ""
    except Exception as e:
        return False, str(e)[:100]

# ---------- 隧道探测 ----------
def tunnel_ok(url):
    try:
        r = urllib.request.urlopen(url+"/ping", timeout=3)
        return b"ok" in r.read(200)
    except Exception:
        return False

def probe():
    ctl = tunnel_ok(CTL)
    pan = tunnel_ok(PANEL)
    return ctl, pan

# ---------- 主循环 ----------
def main():
    st = load_state()
    # 熔断冷却（复用 v13 逻辑）
    if st.get("stopped"):
        sa = st.get("stopped_at", 0)
        elapsed = time.time() - sa
        COOLDOWN = 1800
        if elapsed < COOLDOWN:
            wait = int(COOLDOWN - elapsed)
            log.warning(f"熔断冷却中，还需 {wait//60} 分钟（每 60s 检查登录恢复）")
            end = time.time() + wait
            while time.time() < end:
                time.sleep(60)
                alive, _ = cookie_alive()
                if alive:
                    log.info("登录已恢复，提前解除冷却")
                    break
        st["stopped"] = False; st["fail_streak"] = 0
        save_state(st)

    target = get_target()
    log.info(f"ka_http v3 启动 — 目标会话: {target[:16]}…")
    last_task = 0
    task_idx = st.get("task_idx", -1)
    last_wake = 0
    n = 0

    while True:
        n += 1
        time.sleep(30)
        now = time.time()

        # 1. cookie 活性
        alive, info = cookie_alive()
        if not alive:
            log.error(f"[{n}] cookie 失效（{info}）→ 需要扫码")
            st["fail_streak"] += 1
            if st["fail_streak"] >= 3:
                st["stopped"] = True; st["stopped_at"] = time.time()
                save_state(st)
                log.error("🛑 连续 3 次失效，停止保活（等重新扫码）")
                return
            continue

        # 2. 隧道
        ctl, pan = probe()
        if ctl and pan:
            # 正常 → 轮换任务保活（2~2.5 分钟）
            if now - last_task >= 130:
                task_idx = (task_idx + 1) % len(TASK_TEMPLATES)
                ts = str(int(now))
                text = TASK_TEMPLATES[task_idx].replace("{ts}", ts)
                ok, err = send_sse(target, text)
                if ok:
                    last_task = now
                    log.info(f"[{n}] 任务#{task_idx} 已发送 ✅")
                else:
                    log.error(f"[{n}] 任务发送失败: {err}")
                    st["fail_streak"] += 1
                    if st["fail_streak"] >= 3:
                        st["stopped"]=True; st["stopped_at"]=now; save_state(st)
                        log.error("🛑 熔断：连续失败 3 次")
                        return
            continue

        # 3. 隧道断 → 恢复指令
        if now - last_wake > 180:
            last_wake = now
            log.warning(f"[{n}] 隧道断 (ctl_down={int(not ctl)}, panel_down={int(not pan)}) → 发恢复指令")
            ok, err = send_sse(target, WAKE_CMD)
            if ok:
                log.info(f"[{n}] 恢复指令已发出 ✅")
                st["fail_streak"] = 0
            else:
                st["fail_streak"] += 1
                log.error(f"[{n}] 恢复指令失败 ({st['fail_streak']}/3): {err}")
                if st["fail_streak"] >= 3:
                    st["stopped"]=True; st["stopped_at"]=now; save_state(st)
                    log.error("🛑 熔断：请检查扫码状态")
                    return
        save_state(st)

if __name__ == "__main__":
    main()
