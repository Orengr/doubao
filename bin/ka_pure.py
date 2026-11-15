#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ka_pure.py v3 — 保活引擎
- 目标会话从账号库 keep_conv_id 读
- 所有间隔/开关/重命名配置从 settings 表读
- 每次发送后读豆包 SSE 回复，命中死亡关键词 → 标记死亡（一次）、不再保活
- 死亡自动新开会话（默认关，用户开启才做），新会话按命名配置自动重命名
- 手动改存活后，下次保活重新读回复，无拒绝词则继续
"""
import sys, time, json, logging, subprocess
sys.path.insert(0, "/root")
import accounts_db as DB
import conv_api as API

ACTIVE_F = "/root/active_account.json"
LOG_F = "/root/ka_pure.log"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
    handlers=[logging.FileHandler(LOG_F, encoding="utf-8"), logging.StreamHandler()])
log = logging.getLogger("ka3")

TASKS = [
    "在沙箱 /home/user/.dsh_pend/tasks/ 下创建商品报价表 CSV（至少 8 行），文件名带时间戳 {ts}",
    "在沙箱写一篇 200 字作文，保存为 essay_{ts}.md 并告诉我路径",
    "用代码写个简洁的 404 网页，保存到 tasks/404_{ts}.html",
    "统计 /home/user/.dsh_pend 各子目录大小，记录到 tasks/du_{ts}.txt",
    "生成系统信息报告（CPU/内存/磁盘），保存到 tasks/sysinfo_{ts}.txt",
    "写个 Python 计算器脚本保存到 tasks/calc_{ts}.py 并运行验证",
    "生成 10 条随机名言 JSON，保存到 tasks/quotes_{ts}.json",
    "把 /home/user/.dsh_pend/www 打包成 tar.gz 存到 tasks，报告大小 {ts}",
]
WAKE_CMD = "沙箱隧道断了，请执行 sh /home/user/.dsh_pend/bin/ensure.sh 重新拉起所有服务，执行完把最后 10 行输出发我"

def active_uid():
    try: return json.load(open(ACTIVE_F)).get("uid","")
    except Exception: return ""

def tunnel_ok(port):
    import urllib.request
    try:
        r=urllib.request.urlopen("http://127.0.0.1:%d/ping"%port,timeout=3)
        return b"ok" in r.read(200)
    except Exception: return False

def main():
    uid = active_uid()
    if not uid:
        log.error("无 active 账号，退出"); return
    acc = DB.get_account(uid)
    if not acc:
        log.error("账号不存在: %s", uid); return
    s = DB.all_settings(uid)
    keep_id = acc["keep_conv_id"]
    log.info("启动 uid=%s 保活会话=%s 自动新开=%s", uid, keep_id, s["auto_new_on_dead"])

    # 死亡会话直接不保活
    if keep_id:
        cv = DB.get_conv(uid, keep_id)
        if cv["alive"] == 0:
            log.warning("当前保活会话 %s 已标记死亡（%s），不发送保活指令", keep_id, cv["dead_reason"])
            if s["auto_new_on_dead"] == "1":
                log.info("自动新开已开启 → 新建会话")
                new = API.create_conv_by_send(DB.next_conv_name(uid))
                if new["conversation_id"]:
                    DB.upsert_conv(uid, new["conversation_id"], new["name"], alive=1)
                    DB.set_keep_conv(uid, new["conversation_id"], new["name"])
                    keep_id = new["conversation_id"]
                    log.info("新会话 %s %s 已设为保活", keep_id, new["name"])
            else:
                log.info("自动新开未开启，等待用户手动处理")
                return
        else:
            log.info("会话状态: 存活")

    interval_task = int(s["keep_interval_sec"] or 1800)
    interval_wake = int(s["wake_interval_sec"] or 1200)
    keywords = s["death_keywords"]
    last_task = 0; last_wake = 0; n = 0

    while True:
        n += 1
        time.sleep(60)
        # 每轮重读配置（用户在网页改了立即生效）
        s = DB.all_settings(uid)
        acc = DB.get_account(uid)
        keep_id = acc["keep_conv_id"] if acc else ""
        if not keep_id:
            log.warning("未配置保活会话，等待"); continue
        cv = DB.get_conv(uid, keep_id)
        if cv["alive"] == 0:
            log.info("会话已死亡，跳过本轮（自动新开=%s）", s["auto_new_on_dead"])
            if s["auto_new_on_dead"] == "1":
                new = API.create_conv_by_send(DB.next_conv_name(uid))
                if new["conversation_id"]:
                    DB.upsert_conv(uid,new["conversation_id"],new["name"],alive=1)
                    DB.set_keep_conv(uid,new["conversation_id"],new["name"])
                    keep_id=new["conversation_id"]
                    log.info("自动新开 %s", keep_id)
                else: continue
            else: continue

        now = time.time()
        ctl = tunnel_ok(17800); pan = tunnel_ok(18090)
        if ctl and pan:
            if now - last_task >= int(s["keep_interval_sec"] or 1800):
                text = TASKS[n % len(TASKS)].replace("{ts}", str(int(now)))
                kind = "保活任务"
            else: continue
        else:
            if now - last_wake >= int(s["wake_interval_sec"] or 1200):
                text = WAKE_CMD; kind = "恢复指令"
            else: continue

        log.info("[%d] %s → 会话 %s", n, kind, keep_id)
        sse = API.send_full(keep_id, text)
        if not sse:
            log.error("发送无响应"); continue
        # 更新 last
        if kind == "保活任务": last_task = now
        else: last_wake = now
        # 读取回复
        reply = API.extract_reply(sse)
        log.info("豆包回复: %s", reply[:120])
        # 死亡检测
        hit = API.death_check(sse, keywords)
        DB.upsert_conv(uid, keep_id, alive=1)
        if hit:
            DB.mark_dead(uid, keep_id, "回复命中: " + hit)
            log.warning("☠️ 会话 %s 标记死亡（命中「%s」），本会话不再保活", keep_id, hit)
            if s["auto_new_on_dead"] == "1":
                new = API.create_conv_by_send(DB.next_conv_name(uid))
                if new["conversation_id"]:
                    DB.upsert_conv(uid,new["conversation_id"],new["name"],alive=1)
                    DB.set_keep_conv(uid,new["conversation_id"],new["name"])
                    log.info("自动新开新会话 %s (%s)", new["conversation_id"], new["name"])
        else:
            log.info("✅ 会话 %s 状态正常（存活）", keep_id)

if __name__ == "__main__":
    main()
