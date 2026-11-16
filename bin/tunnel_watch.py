#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tunnel_watch.py v2 — 隧道哨兵（防误判版）
改进：
1. 三路探测（17800 / 18090 / 17801 agent），任一通就算活着
2. 连续 12 次失败（约 12 秒）才判定断开，避免瞬时抖动
3. 拉起后冷却 10 分钟（防轰炸）
4. 拉起前二次确认：再等 3 秒重测，仍失败才发
5. 每日拉起上限 8 次
"""
import sys, time, json, logging, urllib.request
sys.path.insert(0, "/root")
import accounts_db as DB
import conv_api as API

ACTIVE_F = "/root/active_account.json"
LOG_F = "/root/tunnel_watch.log"
STATE_F = "/root/tunnel_watch_state.json"
WAKE_CMD = "沙箱隧道断了，请执行 sh /home/user/.dsh_pend/bin/ensure.sh 重新拉起所有服务，执行完把最后 10 行输出发我"

FAIL_THRESHOLD = 12      # 连续失败 12 次（约12秒）
COOLDOWN = 600           # 拉起后冷却 10 分钟
DAILY_LIMIT = 8          # 每日拉起上限

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.FileHandler(LOG_F, encoding="utf-8")])
log = logging.getLogger("watch")

def probe(port, path="/ping"):
    try:
        r = urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=2)
        b = r.read(300)
        return b"ok" in b or b"true" in b.lower()
    except Exception:
        return False

def alive_tunnel():
    """三路任一通即视为隧道存活"""
    if probe(17800): return True
    if probe(18090, "/cSK41ajJX5"): return True
    try:
        tok = open("/root/sbx_token.txt").read().strip()
        if probe(17801, "/api/ping?token=" + tok): return True
    except Exception:
        pass
    return False

def load_state():
    try: return json.load(open(STATE_F))
    except Exception: return {}

def save_state(st):
    try: json.dump(st, open(STATE_F, "w"))
    except Exception: pass

def active_uid():
    try: return json.load(open(ACTIVE_F)).get("uid", "")
    except Exception: return ""

def main():
    log.info("=== 隧道哨兵 v2 启动（连续%d次失败才拉，冷却%d秒，日限%d次）===",
             FAIL_THRESHOLD, COOLDOWN, DAILY_LIMIT)
    fail_count = 0
    st = load_state()
    today = time.strftime("%Y-%m-%d")
    if st.get("day") != today:
        st = {"day": today, "fired": 0, "last_fire": 0}

    while True:
        time.sleep(1)

        if alive_tunnel():
            if fail_count >= 3:
                log.info("隧道正常（清除 %d 次失败计数）", fail_count)
            fail_count = 0
            continue

        fail_count += 1
        if fail_count < FAIL_THRESHOLD:
            continue

        # 达到阈值，二次确认
        log.warning("连续 %d 次探测失败，3 秒后二次确认…", fail_count)
        time.sleep(3)
        if alive_tunnel():
            log.info("二次确认：隧道其实正常（瞬断），不拉起")
            fail_count = 0
            continue

        now = time.time()
        # 日期滚动
        today = time.strftime("%Y-%m-%d")
        if st.get("day") != today:
            st = {"day": today, "fired": 0, "last_fire": 0}
        if st.get("fired", 0) >= DAILY_LIMIT:
            log.warning("今日已拉起 %d 次，达上限，不再发", DAILY_LIMIT)
            fail_count = 0
            time.sleep(60)
            continue
        if now - st.get("last_fire", 0) < COOLDOWN:
            left = int(COOLDOWN - (now - st.get("last_fire", 0)))
            log.info("冷却中（还剩 %d 秒），跳过", left)
            fail_count = 0
            continue

        uid = active_uid()
        acc = DB.get_account(uid) if uid else None
        cid = acc["keep_conv_id"] if acc else ""
        if not cid:
            log.error("无保活会话，无法拉起")
            fail_count = 0
            continue

        cv = DB.get_conv(uid, cid)
        if cv and cv.get("alive") == 0:
            log.info("保活会话已标记死亡，等自动新建，本轮不发")
            fail_count = 0
            time.sleep(30)
            continue

        log.info("⚡ 确认隧道真断 → 发拉起指令 → %s", cid)
        try:
            sse = API.send_samantha(cid, WAKE_CMD)
            ok = bool(sse) and ("710022002" not in sse) and ("710022004" not in sse)
            log.info("拉起指令: %s (len=%d)", "已发送" if ok else "失败/限流", len(sse or ""))
            if not ok:
                log.warning("响应: %s", (sse or "")[:200])
        except Exception as e:
            log.error("发送异常: %s", str(e)[:200])

        st["fired"] = st.get("fired", 0) + 1
        st["last_fire"] = now
        st["day"] = today
        save_state(st)
        fail_count = 0

if __name__ == "__main__":
    main()
