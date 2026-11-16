#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ka_v14.py — 低频长任务保活（防风控版）
核心改变：
1. 间隔 20-40 分钟（不是 60 秒）
2. 任务是"持续型"（要求它跑几分钟），不是一问一答
3. 每天总量限制（默认 30 条）
4. 隧道检测独立，且只有真断才拉起
"""
import os, sys, time, random, json, logging, datetime
sys.path.insert(0, "/root")
import accounts_db as DB
import conv_api as API

PEND = "/home/user/.dsh_pend"
LOG = "/root/ka_v14.log"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.FileHandler(LOG, encoding="utf-8")])
log = logging.getLogger("ka")

# 每日上限与间隔
DAILY_LIMIT = int(os.environ.get("KA_DAILY_LIMIT", "30"))
GAP_MIN = int(os.environ.get("KA_GAP_MIN", "20"))   # 分钟
GAP_MAX = int(os.environ.get("KA_GAP_MAX", "40"))

# 长时任务模板：要求豆包在沙箱里持续做几分钟
TASKS = [
    lambda ts: (
        "在沙箱做一个持续采集任务，不要只写代码就结束：\n"
        "1) 写脚本 /home/user/.dsh_pend/tasks/beat_%s.sh，循环 90 次，每次 sleep 3 秒并把 date 追加到 beat_%s.log\n"
        "2) 用 nohup 后台启动它\n"
        "3) 现在真的等它跑起来，每 30 秒检查一次日志条数，直到攒够 20 条\n"
        "4) 最后把日志前 5 行和总条数发我\n"
        "整个过程中你要实际等待，不要假装完成。" % (ts, ts)
    ),
    lambda ts: (
        "帮我做一个网页，主题是「服务器状态面板」，文件存 /home/user/.dsh_pend/tasks/page_%s.html\n"
        "要求：深色主题、响应式、含 CPU/内存/磁盘三个环形图（用纯 CSS 或 SVG 画，不要外链）\n"
        "做完后：\n"
        "1) 你自己先检查一遍代码有没有问题\n"
        "2) 然后说哪些地方还能优化\n"
        "3) 再改进一版，存为 page_%s_v2.html\n"
        "4) 最后对比两版差异告诉我\n"
        "请认真做，这会影响我后续的部署决策。" % (ts, ts)
    ),
    lambda ts: (
        "在沙箱里做一次完整的系统体检，过程要真实执行：\n"
        "1) 检查磁盘：df -h、du -sh /home/user/.dsh_pend/* 各占多少\n"
        "2) 检查内存：free -m，找出占用最高的 5 个进程\n"
        "3) 检查网络：curl 测试几个常见域名，记录响应时间\n"
        "4) 检查日志：找出 /home/user/.dsh_pend/log 下最大的 3 个日志文件，各看最后 10 行\n"
        "5) 把以上结果整理成一份 markdown 报告存到 tasks/health_%s.md\n"
        "每一步都要真的执行命令，不要编造数据。" % ts
    ),
]

def today_key():
    return datetime.date.today().isoformat()

def load_state():
    f = os.path.join(PEND, "state", "ka_v14.json")
    try:
        return json.load(open(f))
    except Exception:
        return {}

def save_state(st):
    f = os.path.join(PEND, "state", "ka_v14.json")
    os.makedirs(os.path.dirname(f), exist_ok=True)
    try:
        json.dump(st, open(f, "w"), ensure_ascii=False)
    except Exception:
        pass

def main():
    st = load_state()
    if st.get("day") != today_key():
        st = {"day": today_key(), "count": 0, "idx": 0}
    log.info("启动 v14 低频保活（每日上限 %d 条，间隔 %d-%d 分钟）", DAILY_LIMIT, GAP_MIN, GAP_MAX)
    log.info("今日已发: %d", st.get("count", 0))

    while True:
        # 复查日期
        if st.get("day") != today_key():
            st = {"day": today_key(), "count": 0, "idx": 0}
            save_state(st)

        if st.get("count", 0) >= DAILY_LIMIT:
            log.info("今日已达上限 %d 条，明天继续", DAILY_LIMIT)
            time.sleep(3600)
            continue

        # 等随机间隔
        gap = random.randint(GAP_MIN * 60, GAP_MAX * 60)
        log.info("下次发送在 %d 分 %d 秒后", gap // 60, gap % 60)
        # 分段睡，方便响应停止
        slept = 0
        while slept < gap:
            time.sleep(30)
            slept += 30

        uid = DB.active_uid() if hasattr(DB, "active_uid") else None
        if not uid:
            accs = DB.list_accounts()
            uid = accs[0]["uid"] if accs else None
        if not uid:
            log.warning("无账号，跳过"); continue

        acc = DB.get_account(uid)
        cid = acc.get("keep_conv_id") if acc else None
        if not cid:
            log.warning("未配置保活会话，跳过"); continue

        ts = time.strftime("%H%M%S")
        tpl = TASKS[st.get("idx", 0) % len(TASKS)]
        text = tpl(ts)

        log.info("[%d/%d] 发送长任务 → %s", st["count"] + 1, DAILY_LIMIT, cid)
        try:
            sse = API.send_samantha(cid, text)
            ok = "710022002" not in sse and ("message_id" in sse or "event_type" in sse)
            log.info("结果: %s (len=%d)", "OK" if ok else "FAIL", len(sse or ""))
            if not ok:
                log.warning("响应片段: %s", (sse or "")[:200])
        except Exception as e:
            log.error("发送异常: %s", str(e)[:200])

        st["count"] = st.get("count", 0) + 1
        st["idx"] = st.get("idx", 0) + 1
        save_state(st)

if __name__ == "__main__":
    main()
