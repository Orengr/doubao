#!/usr/bin/env python3
"""
login-guard.py — 登录态守护（中转机侧）

职责：尽一切可能避免 session 被吊销，以及在掉线时自动尝试恢复。

策略：
  1. 每 5 分钟做一次"轻量活动"（访问首页/读会话列表），保持 session 活跃
     —— 但绝不发送消息（发消息才是触发风控的元凶）
  2. 检测到 from_logout / 710012001 → 记录并告警，**不反复重试**
  3. 备份有效 cookie 到多个位置，掉线时可回滚尝试

⚠️ 重要：服务端吊销的 session 无法本地恢复，只能重新扫码。
   本守护的目标是【尽量不吊销】，而不是【吊销后恢复】。
"""
import os
import time
import json
import shutil
import logging
import urllib.request
from datetime import datetime

UNIFIED = "http://127.0.0.1:18800"
CK = "/root/ck_full.txt"
CK_BACKUP_DIR = "/root/ck_backups"
STATE = "/root/login_guard.json"
LOG = "/root/login_guard.log"

os.makedirs(CK_BACKUP_DIR, exist_ok=True)
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.FileHandler(LOG, encoding="utf-8")])
log = logging.getLogger("guard")

CHECK_INTERVAL = 300      # 5 分钟
ALERT_COOLDOWN = 3600     # 告警冷却 1 小时


def api(path, data=None, timeout=40):
    url = f"{UNIFIED}{path}"
    if data is not None:
        req = urllib.request.Request(url, data=json.dumps(data).encode(),
                                     headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    return json.loads(urllib.request.urlopen(url, timeout=timeout).read())


def load_state():
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE))
        except Exception:
            pass
    return {"last_alert": 0, "last_backup": 0, "ok_count": 0, "fail_count": 0}


def save_state(s):
    try:
        json.dump(s, open(STATE, "w"), indent=1)
    except Exception:
        pass


def backup_cookie(s):
    """每次检测正常时备份 cookie，保留最近 10 份"""
    try:
        if not os.path.exists(CK):
            return
        now = time.time()
        if now - s.get("last_backup", 0) < 1800:   # 30 分钟一次
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(CK_BACKUP_DIR, f"ck_{ts}.txt")
        shutil.copy2(CK, dst)
        s["last_backup"] = now
        # 只留 10 份
        files = sorted(os.listdir(CK_BACKUP_DIR))
        for f in files[:-10]:
            try:
                os.remove(os.path.join(CK_BACKUP_DIR, f))
            except Exception:
                pass
    except Exception as e:
        log.warning(f"备份失败: {str(e)[:60]}")


def check_login():
    """
    返回 (alive: bool, detail: str)
    通过 unified /debug 看 URL 与页面状态
    """
    try:
        d = api("/debug", {}, timeout=45)
        info = d.get("info", {}) or {}
        url = info.get("url", "") or ""
        title = info.get("page_title", "") or ""

        if "from_logout" in url:
            return False, "页面被踢回登录（from_logout）"
        if not url or url == "about:blank":
            return None, "浏览器未就绪"

        # 关键：必须用「是否出现登录按钮」判断，不能只看 URL
        # 未登录时页面顶部有独立的"登录"按钮
        info_s = json.dumps(info, ensure_ascii=False)
        # unified 的 debug 返回不含按钮信息，改用 /state
        st = api("/state", timeout=20)
        if st.get("logged") is True:
            return True, f"正常 ({url[:50]})"
        if st.get("status") == "need_qr":
            return False, "需要扫码（unified 报告 need_qr）"
        return None, f"状态不明: {st.get('msg','')[:40]}"
    except Exception as e:
        return None, str(e)[:60]


def wake_activity():
    """
    轻量活动：只读，不发消息
    目的是让 session 保持"被使用"状态
    """
    try:
        api("/sessions", {"op": "refresh"}, timeout=90)
        return True
    except Exception:
        return False


def main():
    log.info("=" * 50)
    log.info("login-guard 启动 — 保持登录活跃（只读，不发消息）")
    log.info("=" * 50)
    s = load_state()

    while True:
        try:
            alive, detail = check_login()

            if alive is True:
                s["ok_count"] = s.get("ok_count", 0) + 1
                backup_cookie(s)
                # 轻量活动，保持活跃
                wake_activity()
                if s["ok_count"] % 12 == 1:
                    log.info(f"登录正常（第 {s['ok_count']} 次检查）")
                s["fail_count"] = 0

            elif alive is False:
                s["fail_count"] = s.get("fail_count", 0) + 1
                log.error(f"⚠ 登录失效: {detail}")

                # 告警（冷却 1 小时）
                now = time.time()
                if now - s.get("last_alert", 0) > ALERT_COOLDOWN:
                    s["last_alert"] = now
                    log.error("=" * 46)
                    log.error("登录已失效，需要人工扫码：")
                    log.error("  打开 http://<中转机IP>:18800/")
                    log.error("  菜单 → 扫码登录 → 获取二维码")
                    log.error("=" * 46)
                    # 让 unified 生成二维码并落盘，方便手机直接打开
                    try:
                        api("/getqr", {}, timeout=90)
                        log.info("已请求生成新二维码")
                        # 等二维码就绪
                        import time as _t
                        for _ in range(20):
                            _t.sleep(3)
                            try:
                                d2 = api("/state", timeout=15)
                                if d2.get("qr_len", 0) > 1000:
                                    log.info(f"✅ 二维码已就绪（{d2['qr_len']} 字节）")
                                    log.info("   手机打开 http://<中转机>:18800/ 扫码即可")
                                    break
                            except Exception:
                                continue
                    except Exception:
                        pass

                # 不反复重试，等 10 分钟
                save_state(s)
                time.sleep(600)
                continue

            else:
                log.warning(f"无法判断登录状态: {detail}")

            save_state(s)
            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            log.error(f"检查异常: {str(e)[:80]}")
            time.sleep(120)


if __name__ == "__main__":
    main()
