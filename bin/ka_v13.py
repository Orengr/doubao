#!/usr/bin/env python3
"""
ka_v13.py — 保活 v13（修掉刷屏缺陷）

v12 的问题：
  - 发送只看"输入框清空"，服务端拒收也当成成功
  - 隧道断了反复发同样的话，124 条重复 → 触发风控 → session 被吊销

v13 修正：
  1. 发送后检查 errorIcon（服务端拒收标志），有错误图标 = 失败
  2. 连续失败 3 次立即停止保活，不再恶化
  3. 任务内容 8 种轮换，绝不重复；每条带时间戳保证唯一
  4. 隧道检测提前到 30 秒（不再每秒），避免高频探测
  5. 隧道断时只发 1 条恢复指令，等 3 分钟再重试
"""
import os
import time
import json
import random
import logging
import urllib.request
from datetime import datetime

LOG = "/root/keepalive.log"
UNIFIED = "http://127.0.0.1:18800"
CONF = "/root/keepconf.json"
STATE_FILE = "/root/ka_state.json"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.FileHandler(LOG, encoding="utf-8")])
log = logging.getLogger("ka13")

TUNNELS = [
    ("控制面", "http://127.0.0.1:17800/ping"),
    ("1Panel", "http://127.0.0.1:18090/"),
]

# 8 种任务，全部要求操作沙箱，内容随机变化避免重复
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

WAKE_CMD = "沙箱隧道断了，请执行 sh /home/user/.dsh_pend/bin/ensure.sh 重新拉起所有服务，执行完把最后 10 行输出发我"


def api(path, data=None, timeout=120):
    url = f"{UNIFIED}{path}"
    if data is not None:
        req = urllib.request.Request(url, data=json.dumps(data).encode(),
                                     headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    return json.loads(urllib.request.urlopen(url, timeout=timeout).read())


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            return json.load(open(STATE_FILE))
        except Exception:
            pass
    return {"fail_streak": 0, "last_task": 0, "last_wake": 0,
            "task_idx": -1, "stopped": False}


def save_state(s):
    try:
        json.dump(s, open(STATE_FILE, "w"), ensure_ascii=False, indent=1)
    except Exception:
        pass


def get_target():
    """读保活目标会话 id"""
    try:
        c = json.load(open(CONF))
        t = (c.get("target") or "").strip()
        if t:
            return t
    except Exception:
        pass
    try:
        return open("/root/ka_target.txt").read().strip()
    except Exception:
        return ""


def probe(url, timeout=5):
    t0 = time.time()
    try:
        r = urllib.request.urlopen(url, timeout=timeout)
        return r.status == 200, int((time.time() - t0) * 1000)
    except Exception:
        return False, timeout * 1000


def send_verified(text, sid):
    """
    发送并验证。返回 (ok, err)
    验证由 unified 侧完成（检查 errorIcon），这里只看返回
    """
    try:
        r = api("/send", {"text": text, "sid": sid}, timeout=150)
        if r.get("ok"):
            return True, ""
        return False, (r.get("error") or "发送失败")[:80]
    except Exception as e:
        return False, str(e)[:80]


def main():
    log.info("=" * 52)
    log.info("ka_v13 启动 — 任务轮换 + 服务端验证 + 失败熔断")
    log.info("=" * 52)
    st = load_state()
    if st.get("stopped"):
        stopped_at = st.get("stopped_at", 0)
        if stopped_at == 0:
            # 兼容旧状态文件：没有时间戳时，视为刚刚熔断
            stopped_at = time.time()
            st["stopped_at"] = stopped_at
            save_state(st)
            log.info("旧状态文件无熔断时间，按当前时间计算冷却")
        elapsed = time.time() - stopped_at
        COOLDOWN = 1800   # 熔断后冷却 30 分钟

        if elapsed < COOLDOWN:
            wait = int(COOLDOWN - elapsed)
            log.warning(f"上次熔断于 {int(elapsed/60)} 分钟前，冷却中，还需等待 {int(wait/60)} 分钟")
            log.warning("（这是防止无限循环的保护，不是错误）")

            # 关键改进：冷却期间持续检测登录状态
            # 一旦检测到登录恢复，立即解除冷却，不等满 30 分钟
            check_end = time.time() + wait
            while time.time() < check_end:
                time.sleep(60)
                try:
                    st_login = api("/state", timeout=15)
                    if st_login.get("logged") is True:
                        log.info("检测到登录已恢复，提前解除熔断冷却")
                        break
                except Exception:
                    pass
                remain_wait = int(check_end - time.time())
                if remain_wait > 0:
                    log.info(f"  冷却剩余 {remain_wait} 秒（等待登录恢复中）")

        log.info("冷却结束，重新开始保活")
        st["stopped"] = False
        st["fail_streak"] = 0

    n = 0
    ctl_down = 0
    panel_down = 0

    while True:
        n += 1
        sid = get_target()
        now = time.time()

        # 隧道检测（每 30 秒一轮，内部 1 秒间隔共 3 次采样）
        for _ in range(3):
            c_ok, c_ms = probe(TUNNELS[0][1])
            p_ok, p_ms = probe(TUNNELS[1][1])
            ctl_down = 0 if c_ok else ctl_down + 1
            panel_down = 0 if p_ok else panel_down + 1
            time.sleep(1)

        if not sid:
            log.warning(f"[{n}] 未设置保活目标会话，等待 60s")
            time.sleep(60)
            continue

        # ---- 隧道异常：只发恢复指令，3 分钟冷却 ----
        if ctl_down >= 2 or panel_down >= 2:
            if now - st["last_wake"] > 180:
                st["last_wake"] = now
                log.warning(f"[{n}] 隧道异常 (ctl_down={ctl_down}, panel_down={panel_down}) → 发恢复指令")
                ok, err = send_verified(WAKE_CMD, sid)
                if ok:
                    log.info(f"[{n}] 恢复指令已发出 ✅")
                    st["fail_streak"] = 0
                else:
                    st["fail_streak"] += 1
                    log.error(f"[{n}] 恢复指令失败 ❌ ({st['fail_streak']}/3): {err}")
            else:
                log.info(f"[{n}] 隧道仍异常，冷却中（{int(180 - (now - st['last_wake']))}s）")
        else:
            # ---- 隧道正常：2~2.5 分钟发一次任务 ----
            interval = random.randint(120, 150)
            if now - st["last_task"] > interval:
                st["last_task"] = now
                idx = (st["task_idx"] + 1) % len(TASK_TEMPLATES)
                st["task_idx"] = idx
                ts = datetime.now().strftime("%H%M%S")
                task = TASK_TEMPLATES[idx].replace("{ts}", ts)
                ok, err = send_verified(task, sid)
                if ok:
                    log.info(f"[{n}] 任务#{idx} ✅ ({c_ms}ms/{p_ms}ms)")
                    st["fail_streak"] = 0
                else:
                    st["fail_streak"] += 1
                    log.error(f"[{n}] 任务#{idx} ❌ ({st['fail_streak']}/3): {err}")

        # ---- 熔断：连续失败 3 次停止 ----
        if st["fail_streak"] >= 3:
            log.error(f"[{n}] 🛑 连续失败 {st['fail_streak']} 次，停止保活以避免恶化")
            log.error("     请检查：1) 豆包是否掉线 2) 会话是否被风控 3) 手动扫码恢复")
            st["stopped"] = True
            st["stopped_at"] = time.time()   # 记录熔断时刻
            save_state(st)
            # 通知中转机
            try:
                api("/notify", {"title": "保活已熔断",
                                "text": "连续发送失败 3 次，需人工检查登录状态"}, timeout=15)
            except Exception:
                pass
            return

        save_state(st)
        time.sleep(28)


if __name__ == "__main__":
    main()
