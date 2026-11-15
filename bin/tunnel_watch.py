#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tunnel_watch.py — 独立隧道哨兵（每秒检测，连续3秒失败秒发拉起指令）
与 ka_pure 完全解耦：ka_pure 只做沙箱小任务保活，本服务只管隧道拉起。
"""
import sys, time, json, logging, urllib.request
sys.path.insert(0, "/root")
import accounts_db as DB
import conv_api as API

ACTIVE_F = "/root/active_account.json"
LOG_F = "/root/tunnel_watch.log"
WAKE_CMD = "沙箱隧道断了，请执行 sh /home/user/.dsh_pend/bin/ensure.sh 重新拉起所有服务，执行完把最后 10 行输出发我"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", handlers=[logging.FileHandler(LOG_F, encoding="utf-8")])

log = logging.getLogger("watch")

def probe(port):
    try:
        r = urllib.request.urlopen("http://127.0.0.1:%d/ping" % port, timeout=1)
        return b"ok" in r.read(200)
    except Exception:
        return False

def active_uid():
    try: return json.load(open(ACTIVE_F)).get("uid","")
    except Exception: return ""

def main():
    uid = active_uid()
    if not uid:
        log.error("无 active 账号，退出"); return
    log.info("隧道哨兵启动 uid=%s（每秒检测 17800/18090，连续3秒失败→秒发拉起）", uid)
    fail_count = 0
    last_fire = 0
    COOLDOWN = 60  # 拉起指令发出后至少 60 秒不重复发

    while True:
        time.sleep(1)
        # 每轮重读账号（自动新建会话后保活目标会变）
        uid = active_uid() or uid
        acc = DB.get_account(uid)
        cid = acc["keep_conv_id"] if acc else ""
        ctl = probe(17800); pan = probe(18090)
        if ctl and pan:
            if fail_count:
                log.info("隧道恢复（连续失败 %d 次清零）", fail_count)
            fail_count = 0
            continue
        fail_count += 1
        log.warning("隧道失败 #%d (17800=%s 18090=%s)", fail_count, ctl, pan)
        if fail_count >= 3:
            now = time.time()
            if now - last_fire < COOLDOWN:
                log.info("冷却中，跳过重复拉起")
                fail_count = 0
                continue
            if not cid:
                log.error("无保活会话，无法发拉起指令")
                fail_count = 0
                continue
            cv = DB.get_conv(uid, cid)
            if cv["alive"] == 0:
                log.warning("保活会话已死亡，先交给 ka_pure 自动新建，本轮不发拉起")
                fail_count = 0
                continue
            log.info("⚡ 连续3秒失败 → 秒发拉起指令 → %s", cid)
            sse = API.send_full(cid, WAKE_CMD)
            last_fire = time.time()
            fail_count = 0
            reply = API.extract_reply(sse) if sse else ""
            if not reply:
                log.error("⚠️ 拉起指令已发但豆包无有效回复（沙箱未执行/实例漂移），不算恢复成功")
            else:
                hit = API.death_check(sse, DB.all_settings(uid)["death_keywords"])
                if hit:
                    DB.mark_dead(uid, cid, "拉起指令命中: " + hit)
                    log.warning("☠️ 拉起指令命中拒绝词，会话标记死亡")
                else:
                    log.info("✅ 拉起指令已发，回复: %s", reply[:80])

if __name__ == "__main__":
    main()
