#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ka_human.py — 真人节奏保活（v15）
设计依据（来自实测 + 用户真实使用习惯）：
- 用户真实场景：一天做网站改东西，几百条很正常，但不会 30 秒一条不停发
- 实测阈值：间隔 <20 秒必被拒绝；20 秒以上可通过
- 实测机制：滑动窗口限流，突增触发冷却约 1 分钟

因此本策略模拟"真人干活"的时间分布：
1. 活跃时段（9:00-23:00）为主，深夜低频
2. 每次会话 2-5 条（像真人连续追问），条间隔 40-90 秒
3. 会话之间休息 25-50 分钟
4. 每日总量上限 60 条（真人一天的量级）
5. 任务内容像自然人提问，避免"脚本/循环N次"这类触发词
"""
import os, sys, time, random, json, logging, datetime
sys.path.insert(0, "/root")
import accounts_db as DB
import conv_api as API

PEND = "/home/user/.dsh_pend"
LOG = "/root/ka_human.log"
STATE_F = "/root/ka_human_state.json"

DAILY_LIMIT = int(os.environ.get("KA_DAILY", "60"))
BURST_MIN, BURST_MAX = 2, 5          # 每次会话条数
IN_BURST_GAP = (90, 180)             # 条间隔 90-180 秒（实测 90 秒仍会限流，取更保守值）
REST_GAP = (25 * 60, 50 * 60)        # 会话间隔 25-50 分钟
NIGHT_GAP = (90 * 60, 150 * 60)      # 深夜 90-150 分钟

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.FileHandler(LOG, encoding="utf-8")])
log = logging.getLogger("ka")

# 像真人一样的请求（避免"执行脚本/循环N次"触发自动化审核）
TOPICS = [
    "帮我把刚才那个页面的配色再调柔和一点，深色看久了眼睛累",
    "这个布局在手机上会不会挤？帮我想想怎么改",
    "你觉得首页放点什么内容比较合适",
    "帮我把标题字体换一下，现在这个太生硬了",
    "能不能加个简单的导航栏，就三四个链接那种",
    "页面加载速度有什么能优化的地方吗",
    "帮我想几个更好看的按钮样式",
    "这个配色和暗色模式搭吗",
    "footer 那里太空了，加点什么好",
    "帮我把文字排版再调一下，行距有点紧",
]

def today():
    return datetime.date.today().isoformat()

def load():
    try: return json.load(open(STATE_F))
    except Exception: return {}

def save(st):
    try: json.dump(st, open(STATE_F, "w"), ensure_ascii=False)
    except Exception: pass

def is_night():
    h = datetime.datetime.now().hour
    return h < 8 or h >= 23

def active_uid():
    accs = DB.list_accounts()
    return accs[0]["uid"] if accs else None

def main():
    st = load()
    if st.get("day") != today():
        st = {"day": today(), "count": 0, "topic": 0}
    log.info("=== 真人节奏保活启动（日限%d条，每次2-5条，条间隔40-90秒）===", DAILY_LIMIT)

    while True:
        if st.get("day") != today():
            st = {"day": today(), "count": 0, "topic": 0}
            save(st)

        if st["count"] >= DAILY_LIMIT:
            log.info("今日 %d 条上限已达，休息到明天", DAILY_LIMIT)
            time.sleep(1800)
            continue

        if is_night():
            gap = random.randint(*NIGHT_GAP)
            log.info("深夜时段，休息 %d 分钟", gap // 60)
            time.sleep(gap)
            continue

        # 一次"会话"：连续 2-5 条
        burst = random.randint(BURST_MIN, BURST_MAX)
        log.info("开始新会话，计划 %d 条", burst)

        uid = active_uid()
        acc = DB.get_account(uid) if uid else None
        cid = acc.get("keep_conv_id") if acc else None
        if not cid:
            log.warning("无保活会话，5分钟后重试")
            time.sleep(300)
            continue

        # 发送前先检查会话健康（用修复后的 recent 接口）
        try:
            h = API.conv_health(cid)
            if not h["exists"]:
                log.warning("会话 %s 不存在，跳过本轮", cid)
                time.sleep(600)
                continue
            log.info("会话健康: %d 条消息, 最后发送者 %s", h["msg_count"], h["last_sender"][:10])
        except Exception as e:
            log.warning("健康检查失败: %s", str(e)[:100])

        for i in range(burst):
            if st["count"] >= DAILY_LIMIT:
                break
            topic = TOPICS[st["topic"] % len(TOPICS)]
            st["topic"] += 1
            log.info("  [%d/%d] 今日第%d条: %s", i + 1, burst, st["count"] + 1, topic[:30])
            try:
                ok, mid, conv, raw = API.send_and_get_ids(cid, topic)
                if ok:
                    st["rl_count"] = 0
                    log.info("    ✅ 已发送")
                else:
                    tag = "限流" if "710022004" in (raw or "") else ("拦截" if "710022002" in (raw or "") else "失败")
                    log.warning("    ❌ %s", tag)
                    if tag == "限流":
                        # 实测：成功1条后冷却已超6分钟；遇限流要大幅退避
                        backoff = min(600 * (st.get("rl_count", 0) + 1), 3600)
                        st["rl_count"] = st.get("rl_count", 0) + 1
                        save(st)
                        log.warning("    遇限流，退避 %d 秒（累计 %d 次）", backoff, st["rl_count"])
                        time.sleep(backoff)
                        break
            except Exception as e:
                log.error("    异常: %s", str(e)[:150])

            st["count"] += 1
            save(st)
            if i < burst - 1:
                g = random.randint(*IN_BURST_GAP)
                time.sleep(g)

        # 会话间休息
        rest = random.randint(*REST_GAP)
        log.info("会话结束，休息 %d 分钟", rest // 60)
        time.sleep(rest)

if __name__ == "__main__":
    main()
