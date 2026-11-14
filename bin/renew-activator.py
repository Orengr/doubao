#!/usr/bin/env python3
"""
renew-activator.py — 主动续期器（中转机侧）

背景（实测数据）：
  sid_guard 有效期 21600 秒（6 小时）
  指纹历史显示每次变化间隔接近 6 小时 → 一直在卡过期边缘
  过期后访问不再续期 → 直接掉线

本脚本：在过期前主动触发续期，绝不等到临界点。

原理：
  豆包网页在「有交互」时才会刷新 sid_guard
  只读访问（GET 页面）不触发续期
  需要触发的是「会话列表刷新」这类 API 请求

策略：
  每 20 分钟执行一次 /sessions refresh（触发 API 调用）
  同时解析 sid_guard 剩余时间，少于 60 分钟时加密频率
"""
import os
import re
import time
import json
import hashlib
import sqlite3
import logging
import urllib.request
from datetime import datetime

UNIFIED = "http://127.0.0.1:18800"
PROFILE_DB = "/root/doubao_profile/Default/Cookies"
STATE = "/root/renew_state.json"
LOG = "/root/renew.log"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.FileHandler(LOG, encoding="utf-8")])
log = logging.getLogger("renew")

# Chromium Linux cookie 解密
KEY = hashlib.pbkdf2_hmac('sha1', b'peanuts', b'saltysalt', 1, 16)
IV = b' ' * 16


def read_sid_guard():
    """
    解密读 sid_guard，返回 (session_id, expire_ts, ttl) 或 None

    结构（实测确认）：
      <sessionid>|<过期时间戳>|<TTL秒>|<HTTP日期>
    例：
      <sid>|<过期时间戳>|<TTL>|<HTTP日期>

    注意：
      - 字段2 是【过期时间戳】（不是创建时间）
      - 字段3 是 TTL 总长度
      - 字段4 是 Cookie 的绝对过期日期，但 session 按字段2 判断
    """
    try:
        from Crypto.Cipher import AES
        c = sqlite3.connect(PROFILE_DB)
        row = c.execute("SELECT encrypted_value FROM cookies WHERE name='sid_guard'").fetchone()
        c.close()
        if not row or not row[0]:
            return None
        enc = row[0]
        d = AES.new(KEY, AES.MODE_CBC, IV).decrypt(enc[3:])
        pad = d[-1] if 0 < d[-1] < 16 else 0
        d = d[:-pad] if pad else d
        s = d.decode('utf-8', 'ignore')
        m = re.search(r'([0-9a-f]{32})%7C(\d+)%7C(\d+)', s)
        if m:
            return (m.group(1), int(m.group(2)), int(m.group(3)))
        return None
    except Exception as e:
        log.debug(f"读取失败: {str(e)[:50]}")
        return None


def api(path, data=None, timeout=90):
    url = f"{UNIFIED}{path}"
    if data is not None:
        req = urllib.request.Request(url, data=json.dumps(data).encode(),
                                     headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    return json.loads(urllib.request.urlopen(url, timeout=timeout).read())


def trigger_activity(level=1):
    """
    触发续期，level 越高交互越强

    level 1: 刷新会话列表（轻量 API 调用）
    level 2: 打开对话页 + 刷新列表
    level 3: 发送一条消息（最强交互，但会消耗额度）
    """
    try:
        if level >= 2:
            # 中等等级：让浏览器真正加载页面
            try:
                api("/refresh", {}, timeout=90)
            except Exception:
                pass

        if level >= 3:
            # 高强度：发一条真实消息
            try:
                api("/send", {"text": "在沙箱执行 date 并回复结果"}, timeout=120)
                return True, "level3"
            except Exception as e:
                return False, str(e)[:60]

        r = api("/sessions", {"op": "refresh"}, timeout=120)
        return bool(r.get("ok")), r.get("error", "")
    except Exception as e:
        return False, str(e)[:60]


def main():
    log.info("=" * 52)
    log.info("renew-activator 启动 — 主动续期，避免卡过期边缘")
    log.info("=" * 52)

    last_activity = 0
    fail_streak = 0
    streak_ok = 0
    no_effect = 0

    while True:
        try:
            info = read_sid_guard()
            now = time.time()

            if info:
                sid, exp_ts, ttl = info
                remain = exp_ts - now
                remain_min = int(remain / 60)

                # 按 TTL 比例计算续期时机（适配任意有效期：6小时 / 30天 / ...）
                # 原则：消耗超过 50% 就开始续期，避免卡过期边缘
                used_ratio = 1.0 - (remain / ttl) if ttl > 0 else 1.0

                if remain <= 0:
                    # 已过期
                    interval = 300
                    urgent = True
                    log.warning("  已过期，每 5 分钟尝试一次")
                elif used_ratio > 0.85:
                    # 已用 85%+ → 紧急
                    interval = max(300, int(ttl * 0.02))    # TTL 的 2%
                    urgent = True
                elif used_ratio > 0.60:
                    # 已用 60%+ → 加密
                    interval = max(600, int(ttl * 0.05))    # TTL 的 5%
                    urgent = True
                else:
                    # 还早 → 常规
                    interval = max(1800, int(ttl * 0.10))   # TTL 的 10%
                    urgent = False

                # 上限：短 TTL 最多 2 小时，长 TTL 允许更长间隔
                max_iv = 7200 if ttl < 86400 else min(int(ttl * 0.15), 43200)
                interval = min(interval, max_iv)
                if urgent:
                    log.info(f"  剩余 {remain_min} 分钟（已用 {used_ratio*100:.0f}%），"
                             f"续期间隔 {interval//60} 分钟")

                if now - last_activity > interval:
                    # 根据连续失败次数提升交互强度
                    lvl = 1 if fail_streak == 0 else (2 if fail_streak < 3 else 3)
                    ok, err = trigger_activity(level=lvl)
                    if ok:
                        last_activity = now
                        fail_streak = 0
                        log.info(f"续期触发 ✅ 剩余 {remain_min} 分钟"
                                 f"{' (紧急)' if urgent else ''}")
                        # 验证续期是否真的生效
                        time.sleep(5)
                        info2 = read_sid_guard()
                        if info2 and info2[1] > exp_ts + 60:
                            new_exp = datetime.fromtimestamp(info2[1]).strftime('%m-%d %H:%M')
                            extended = int((info2[1] - exp_ts) / 60)
                            log.info(f"  ⏰ 续期成功：有效期延长 {extended} 分钟 → {new_exp}")
                            streak_ok += 1
                        elif info2 and info2[1] == exp_ts:
                            log.warning(f"  ⚠ 有效期未变（可能需更强交互）")
                            no_effect += 1
                            if no_effect >= 3:
                                log.error("  连续 3 次续期无效，尝试刷新页面")
                                try:
                                    api("/refresh", {}, timeout=60)
                                except Exception:
                                    pass
                                no_effect = 0
                    else:
                        fail_streak += 1
                        log.warning(f"续期失败 ({fail_streak}): {err[:60]}")
                        if fail_streak >= 5:
                            log.error("连续 5 次续期失败，登录可能已失效")
                            fail_streak = 0
            else:
                log.warning("无法读取 sid_guard")

            time.sleep(120)

        except Exception as e:
            log.error(f"异常: {str(e)[:80]}")
            time.sleep(180)


if __name__ == "__main__":
    main()
