#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ka_pure.py v6 — 纯保活引擎（只做沙箱小任务，不检测隧道、不发恢复指令）
隧道检测与拉起由独立 tunnel_watch.py 负责。
"""
import sys, time, json, logging, random
sys.path.insert(0, "/root")
import accounts_db as DB
import conv_api as API

ACTIVE_F = "/root/active_account.json"
LOG_F = "/root/ka_pure.log"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", handlers=[logging.FileHandler(LOG_F, encoding="utf-8")])

log = logging.getLogger("ka6")

# 沙箱内的小任务：保持实例活跃，无恢复、无高风险操作
TASKS = [
    "在沙箱 /home/user/.dsh_pend/tasks/ 生成 99 乘法表，保存为 multiply_{ts}.txt",
    "用几行 HTML+CSS 写一个简洁的 404 页面，保存到 tasks/404_{ts}.html",
    "在沙箱生成系统信息小报告（uname、内存、磁盘），保存到 tasks/sysinfo_{ts}.txt",
    "写个 Python 计算器脚本（加减乘除）保存到 tasks/calc_{ts}.py 并运行验证",
    "生成 10 条随机励志名言，保存 JSON 到 tasks/quotes_{ts}.json",
    "在 tasks/ 下创建商品报价表 CSV（至少 8 行），文件名带时间戳 {ts}",
    "写一篇 100 字小作文，主题随机，保存到 tasks/essay_{ts}.md",
    "把 /home/user/.dsh_pend 目录树列出来保存到 tasks/tree_{ts}.txt",
]

def active_uid():
    try: return json.load(open(ACTIVE_F)).get("uid","")
    except Exception: return ""

def main():
    uid = active_uid()
    if not uid:
        log.error("无 active 账号，退出"); return
    acc = DB.get_account(uid)
    if not acc or not acc["keep_conv_id"]:
        log.error("账号或保活会话未配置，退出"); return
    log.info("启动 纯保活 uid=%s 会话=%s（小任务每3-5分钟随机一次，不管隧道）", uid, acc["keep_conv_id"])
    last_task = 0; n = 0
    next_gap = random.randint(60, 90)  # 3~5 分钟内随机

    while True:
        n += 1
        time.sleep(10)  # 每 30 秒检查一次是否到间隔
        s = DB.all_settings(uid)
        acc = DB.get_account(uid)
        cid = acc["keep_conv_id"] if acc else ""
        if not cid:
            log.warning("未配置保活会话，等待"); continue
        # 每轮强制重读会话状态（防止上一轮 upsert 覆盖标死状态）
        c = DB.conn(); row = c.execute("SELECT alive,dead_reason FROM conv_status WHERE uid=? AND conv_id=?",(uid,cid)).fetchone(); c.close()
        cv_alive = row["alive"] if row else 1
        cv_reason = row["dead_reason"] if row else ""
        if cv_alive == 0:
            if s["auto_new_on_dead"] == "1":
                name = DB.next_conv_name(uid)
                new = API.create_conv_by_send(name)
                if new["conversation_id"]:
                    DB.upsert_conv(uid, new["conversation_id"], name, alive=1)
                    DB.set_keep_conv(uid, new["conversation_id"], name)
                    log.info("☠️ 会话死亡 → 自动新建 %s (%s) 并设为保活", new["conversation_id"], name)
                    cid = new["conversation_id"]
                else:
                    log.error("自动新建失败: %s", new.get("hint","")); continue
            else:
                log.info("会话已死亡（%s）且自动新开关闭，本轮跳过", cv_reason); continue

        now = time.time()
        if now - last_task < next_gap:
            continue
        text = TASKS[n % len(TASKS)].replace("{ts}", str(int(now)))
        log.info("[%d] 保活小任务 → %s", n, cid)
        sse = API.send_full(cid, text)
        if not sse:
            log.error("发送无有效回复（未落库）"); continue
        last_task = now
        next_gap = random.randint(180, 300)  # 本次完成后重新抽 3~5 分钟
        log.info("下一次小任务将在 %d 秒后（维持沙箱活跃）", next_gap)
        reply = API.extract_reply(sse)
        log.info("豆包回复: %s", reply[:100])
        hit = API.death_check(sse, s["death_keywords"])
        if hit:
            DB.mark_dead(uid, cid, "保活任务命中: " + hit)
            log.warning("☠️ 会话 %s 标记死亡（%s）", cid, hit)
        else:
            DB.upsert_conv(uid, cid, alive=1)
            log.info("✅ 保活任务完成，会话存活")

if __name__ == "__main__":
    main()
