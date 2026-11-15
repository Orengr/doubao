#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ka_pure.py — 纯接口保活引擎（无浏览器、无UI、无扫码）

链路：短信登录(一次性) → 有效cookie → doubao2api DoubaoChatClient → 发送
"""
import asyncio, json, os, sys, time, logging

# 添加 doubao2api 路径
sys.path.insert(0, '/root/doubao2api')
from doubao2api.client import DoubaoChatClient

CK_FILE = os.environ.get('CK_FILE', '/root/ck_sms_auto.txt')
STATE_F = os.environ.get('KA_STATE', '/root/ka_state.json')
CONF_F = os.environ.get('KA_CONF', '/root/keepconf.json')
LOG_F = os.environ.get('KA_LOG', '/root/ka_pure.log')

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_F, encoding="utf-8"), logging.StreamHandler()])
log = logging.getLogger("ka_pure")

TASKS = [
    "在沙箱 /home/user/.dsh_pend/tasks/ 下创建一个商品报价表 CSV（商品名、单价、数量、总价），至少 8 行，文件名带时间戳 {ts}",
    "在沙箱 /home/user/.dsh_pend/tasks/ 下写一篇 200 字作文，主题随机，保存为 essay_{ts}.md 并告诉我路径",
    "用几行代码写一个简洁的网页 404 界面（带样式和返回按钮），保存到 /home/user/.dsh_pend/tasks/404_{ts}.html",
    "在沙箱统计 /home/user/.dsh_pend 下各子目录大小，从大到小列出前 10 名，记录到 tasks/du_{ts}.txt",
    "在沙箱生成一份系统信息报告（CPU 核数、内存、磁盘、运行时长），保存到 tasks/sysinfo_{ts}.txt",
    "在沙箱写一个 Python 计算器脚本（支持加减乘除），保存到 tasks/calc_{ts}.py 并运行一次验证",
    "在沙箱生成 10 条随机励志名言，保存为 JSON 到 tasks/quotes_{ts}.json",
    "在沙箱用 bash 把 /home/user/.dsh_pend/www 打包成 tar.gz 存到 tasks，并报告压缩包大小 {ts}",
]
WAKE_CMD = "沙箱隧道断了，请执行 sh /home/user/.dsh_pend/bin/ensure.sh 重新拉起所有服务，执行完把最后 10 行输出发我"

def load_cookies():
    ck = {}
    for line in open(CK_FILE):
        line = line.strip()
        if '=' in line:
            k, v = line.split('=', 1)
            ck[k] = v
    return ck

def load_state():
    try: return json.load(open(STATE_F))
    except: return {"fail_streak":0,"last_task":0,"last_wake":0,"task_idx":-1}

def save_state(st): json.dump(st, open(STATE_F,'w'), ensure_ascii=False, indent=1)

def get_target():
    try: return json.load(open(CONF_F)).get("target","")
    except: return ""

def tunnel_ok(url):
    import urllib.request
    try:
        r = urllib.request.urlopen(url+'/ping', timeout=3)
        return b'ok' in r.read(200)
    except: return False

async def send_and_get_reply(client, text, timeout_s=60):
    full = ''
    try:
        async for chunk in client.chat_stream(text):
            t = getattr(chunk, 'text', '')
            if t: full += t
            if f'OK{int(time.time())}' in full: break
            if time.time() - time.time() > timeout_s: break
    except Exception as e:
        return False, str(e)[:150], full
    return True, '', full

async def main():
    st = load_state()
    target = get_target()
    log.info(f"ka_pure 启动 — 目标: {target[:20]}")
    cookies = load_cookies()
    ms_token = cookies.get('msToken', '')
    task_idx = st.get('task_idx', -1)
    last_task = 0
    last_wake = 0
    
    async with DoubaoChatClient(
        cookies=cookies, ms_token=ms_token,
        device_id='7707456447802197504',
        web_id='7708252047023523337',
        fp='verify_mwea228o_WY5ckeMo_3xNI_4v83_AnQH_LKQ7pl55QA3v',
    ) as client:
        log.info("客户端就绪")
        n = 0
        while True:
            n += 1
            time.sleep(30)
            now = time.time()
            
            ctl = tunnel_ok('http://127.0.0.1:17800')
            pan = tunnel_ok('http://127.0.0.1:18090')
            
            if ctl and pan:
                # 正常 → 保活任务
                if now - last_task >= 130:
                    task_idx = (task_idx + 1) % len(TASKS)
                    ts = str(int(now))
                    text = TASKS[task_idx].replace("{ts}", ts)
                    ok, err, reply = await send_and_get_reply(client, text)
                    if ok:
                        last_task = now
                        st['fail_streak'] = 0
                        log.info(f"[{n}] 任务#{task_idx} ✅ 回复: {reply[:60]}")
                    else:
                        st['fail_streak'] = st.get('fail_streak',0)+1
                        log.error(f"[{n}] 任务失败: {err}")
            else:
                # 隧道断 → 恢复指令
                if now - last_wake > 180:
                    last_wake = now
                    log.warning(f"[{n}] 隧道断 → 发恢复指令")
                    ok, err, reply = await send_and_get_reply(client, WAKE_CMD)
                    if ok:
                        log.info(f"[{n}] 恢复指令已发出 ✅ 回复: {reply[:80]}")
                    else:
                        st['fail_streak'] = st.get('fail_streak',0)+1
                        log.error(f"[{n}] 恢复失败: {err}")
                        if st['fail_streak'] >= 5:
                            log.error("🛑 熔断")
                            break
            
            st['task_idx'] = task_idx
            save_state(st)

if __name__ == '__main__':
    asyncio.run(main())
