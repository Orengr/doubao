#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sbx_guard.py — 沙箱实例守护（服务器侧运行）
检测实例重建（host 变化 / agent 失联）→ 秒级自动恢复：
  1) 拉起 sbx_agent（面板能力层）
  2) 确保 frpc 隧道在线
  3) 恢复持久卷数据软链（如 www、站点）
  4) 记录事件
"""
import os, time, json, subprocess, urllib.request, logging

CTL = "http://127.0.0.1:17800"
AGENT = "http://127.0.0.1:17999"
TOKEN_FILE = "/root/sbx_token.txt"
LOG_F = "/root/sbx_guard.log"
STATE_F = "/root/sbx_guard_state.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.FileHandler(LOG_F, encoding="utf-8")])
log = logging.getLogger("guard")

def token():
    try: return open(TOKEN_FILE).read().strip()
    except Exception: return ""

def ctl_sh(cmd, t=60):
    try:
        u = CTL + "/sh?token=" + token() + "&t=" + str(t)
        req = urllib.request.Request(u, data=cmd.encode(), method="POST")
        with urllib.request.urlopen(req, timeout=t + 15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"rc": -1, "out": "ERR " + str(e)[:120]}

def state():
    try: return json.load(open(STATE_F))
    except Exception: return {}

def save(st):
    try: json.dump(st, open(STATE_F, "w"), ensure_ascii=False)
    except Exception: pass

def ctl_host():
    try:
        return json.loads(urllib.request.urlopen(CTL + "/ping", timeout=5).read().decode()).get("host", "")
    except Exception:
        return ""

def agent_ok():
    try:
        r = json.loads(urllib.request.urlopen(AGENT + "/api/ping?token=" + token(), timeout=5).read().decode())
        return bool(r.get("ok"))
    except Exception:
        return False

RECOVER = r'''
set -e
PEND=/home/user/.dsh_pend
mkdir -p $PEND/log $PEND/state
# 1) agent 代码
if [ ! -f $PEND/bin/sbx_agent.py ]; then echo "NO_AGENT_CODE"; fi
# 2) 启动 agent（若未运行）
if ! pgrep -f "sbx_agent.py" >/dev/null 2>&1; then
  cd $PEND && setsid nohup python3 $PEND/bin/sbx_agent.py >> $PEND/log/sbx_agent.log 2>&1 < /dev/null &
  sleep 2
fi
# 3) frpc
if ! pgrep -x frpc >/dev/null 2>&1; then
  cd $PEND/frp && setsid nohup ./frpc -c frpc.toml >> $PEND/log/frpc.log 2>&1 < /dev/null &
  sleep 2
fi
# 4) www 软链（如有数据）
if [ -d $PEND/www ] && [ ! -e /www ]; then ln -sfn $PEND/www /www 2>/dev/null || sudo -n ln -sfn $PEND/www /www 2>/dev/null || true; fi
echo "RECOVER_DONE"
'''

def main():
    log.info("sbx_guard 启动")
    last_host = ""
    recover_count = 0
    while True:
        time.sleep(5)
        h = ctl_host()
        st = state()
        if not h:
            # 控制面不可达 = 实例没了/正在重建
            if st.get("last_state") != "down":
                log.warning("控制面不可达，等待实例恢复")
                save({"last_state": "down", "at": int(time.time())})
            continue
        if st.get("last_state") == "down":
            log.info("实例已恢复: %s", h)
            save({"last_state": "up", "host": h, "at": int(time.time())})
        if h != last_host:
            if last_host:
                log.info("⚡ 检测到实例变化 %s → %s，开始自动恢复", last_host, h)
            else:
                log.info("当前实例: %s", h)
            last_host = h
            r = ctl_sh(RECOVER, 90)
            out = (r.get("out") or "")
            ok = "RECOVER_DONE" in out
            log.info("恢复结果: %s %s", "OK" if ok else "FAIL", out[-200:].replace("\n", " | "))
            # 恢复后确认 agent
            for _ in range(6):
                if agent_ok(): break
                time.sleep(3)
            log.info("agent 状态: %s", "在线" if agent_ok() else "离线")
            recover_count += 1
            save({"last_state": "up", "host": h, "at": int(time.time()), "recovers": recover_count})

if __name__ == "__main__":
    main()
