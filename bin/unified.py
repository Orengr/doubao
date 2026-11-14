#!/usr/bin/env python3
"""
unified.py — 统一控制台（合并登录 + 监控）

端口：18800
页面：汉堡菜单切换「扫码登录 / 邮件配置 / 状态监控」
"""
import os, json, time, threading, importlib.util, logging, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

PORT = 18800
PROFILE = "/root/doubao_profile"
CK_FILE = "/root/ck_full.txt"
CONF = "/root/healthconf.json"
# 可选：外部 CF 域名检测（不配置就不检测，避免硬编码任何域名）
CF_DOMAIN = os.environ.get("CF_DOMAIN", "").strip()

STATE = {"qr": b"", "status": "init", "msg": "启动中…", "logged": False, "busy": False}
PG = {"page": None}          # 全局浏览器页面引用
SEND_QUEUE = []              # 待发消息队列
SEND_LOCK = threading.Lock()
QR_TS = {"last": 0}
SYNC_TS = {"last": 0}
KEEP_CONF = "/root/keepconf.json"
NEWCHAT = {"active": False}   # 新会话模式：为 True 时 ensure_session 不跳旧会话
# ===== 硬性禁令：keepconf 中 alive=False 的会话禁止发送 =====
HARD_BANNED = {"38453442383066370"}   # 永久禁令（一键关闭视频脚本）


def banned_ids():
    """只拦永久禁令会话（一键关闭视频脚本），其余一律放行"""
    return set(HARD_BANNED)


def is_banned(pg):
    """检查当前页面是否位于禁发会话（精确匹配 URL 末尾的会话 id）"""
    try:
        import re as _r
        url = pg.url or ""
        m = _r.search(r"/chat/(\d{10,})", url)
        if not m:
            return False          # 不在任何会话页（首页等）→ 不禁止
        sid = m.group(1)
        return sid in banned_ids()
    except Exception:
        return False


def load_keepconf():
    if os.path.exists(KEEP_CONF):
        try:
            c = json.load(open(KEEP_CONF))
            # 清理非数字 id（侧边栏噪音项）
            ss = c.get("sessions") or {}
            c["sessions"] = {k: v for k, v in ss.items() if str(k).isdigit()}
            if c.get("target") and not str(c["target"]).isdigit():
                c["target"] = ""
            return c
        except Exception:
            pass
    return {"sessions": {}, "target": ""}


def save_keepconf(c):
    try:
        json.dump(c, open(KEEP_CONF, "w"), ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_hc():
    spec = importlib.util.spec_from_file_location("hc", "/root/healthcheck.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


KEY_GROUPS = {
    "session": ["sessionid_ss", "sessionid"],
    "guard":   ["sid_guard", "sid_ss"],
    "uid":     ["uid_tt_ss", "uid_tt"],
}


def _is_complete(cookie_map):
    """判断 cookie 集合是否完整（每组至少有一个）"""
    for names in KEY_GROUPS.values():
        if not any(n in cookie_map for n in names):
            return False
    return True


def save_cookie(ctx, force=False):
    """
    保存 cookie —— 只在完整时覆盖，避免用残缺集合覆盖好数据
    """
    try:
        cks = ctx.cookies()
        pairs = [f"{c['name']}={c['value']}" for c in cks
                 if "doubao" in c.get("domain", "") or "bytedance" in c.get("domain", "")]
        if not pairs:
            return 0
        cmap = {}
        for p in pairs:
            if "=" in p:
                k, v = p.split("=", 1)
                cmap[k] = v

        # 完整性检查
        if not _is_complete(cmap) and not force:
            return 0    # 拒绝覆盖

        # 备份旧文件
        if os.path.exists(CK_FILE):
            try:
                import shutil
                shutil.copy2(CK_FILE, CK_FILE + ".bak")
            except Exception:
                pass

        open(CK_FILE, "w").write("\n".join(pairs))
        return len(pairs)
    except Exception:
        return 0


def grab_qr(pg):
    """
    抓二维码元素
    实测豆包的二维码选择器：[class*="qr"]，尺寸约 164x162
    """
    try:
        # 精确选择器（实测有效）
        for sel in ['[class*="qr"]', '[class*="Qr"]', '[class*="QR"]',
                    'img[src*="qr"]', 'canvas']:
            try:
                els = pg.locator(sel)
                cnt = els.count()
            except Exception:
                continue
            best = None
            for i in range(min(cnt, 12)):
                try:
                    el = els.nth(i)
                    box = el.bounding_box()
                    if not box:
                        continue
                    w, h = box["width"], box["height"]
                    # 二维码特征：接近正方形，尺寸 100~400
                    if 100 < w < 400 and 100 < h < 400 and abs(w - h) < 30:
                        if best is None or w > best[0]:
                            best = (w, el)
                except Exception:
                    continue
            if best:
                return best[1].screenshot()
        return b""
    except Exception:
        return b""


SESSION_NAME = "短视频脚本设计"


def _cookie_logged(ctx):
    """
    用 cookie 判断登录（最可靠，不受页面渲染影响）
    关键 cookie 存在 → 已登录
    """
    try:
        cks = {c["name"]: c["value"] for c in ctx.cookies()}
        # 新体系
        if cks.get("sessionid_ss") or cks.get("sessionid"):
            if cks.get("sid_guard") or cks.get("sid_ucp_v1"):
                return True
        return False
    except Exception:
        return False


def is_logged_in(pg, ctx=None):
    """
    综合判断登录状态
    优先 cookie（最准），其次页面元素
    """
    # 双重验证：cookie 存在 且 页面无"登录"按钮
    # （session 被服务端吊销时，cookie 仍在本地，但页面显示"登录"）
    try:
        has_cookie = False
        if ctx is not None:
            has_cookie = _cookie_logged(ctx)

        # 页面验证：顶部"登录"按钮可见 = 未登录
        login_btn = pg.locator('button:has-text("登录")')
        for i in range(min(login_btn.count(), 4)):
            try:
                el = login_btn.nth(i)
                if el.is_visible(timeout=600):
                    box = el.bounding_box()
                    if box and box.get("y", 999) < 200 and box.get("width", 999) < 150:
                        return False   # 页面明确显示未登录（最可靠）
            except Exception:
                continue

        # 页面无登录按钮：
        if has_cookie:
            return True    # cookie 有 + 无登录按钮 = 已登录
        return None        # cookie 没有 + 无按钮 = 不确定
    except Exception:
        return None


def close_popups(pg):
    """关闭推广浮层等遮挡物"""
    try:
        for sel in ['text=下次提醒我', 'text=稍后再说', 'text=关闭',
                    '[class*="close"] svg', '[class*="Close"] svg']:
            try:
                loc = pg.locator(sel).first
                if loc.count() and loc.is_visible(timeout=1200):
                    loc.click(timeout=2000)
                    pg.wait_for_timeout(600)
            except Exception:
                continue
    except Exception:
        pass


def ensure_session(pg, force_session=None):
    """
    确保页面可发送消息。
    原则：绝不擅自切换会话——页面在哪就在哪发。
    只有显式传入 force_session（会话 id）时才跳转。
    """
    try:
        close_popups(pg)
        # 显式指定会话时才跳转
        if force_session:
            pg.goto(f"https://www.doubao.com/chat/{force_session}",
                    timeout=60000, wait_until="domcontentloaded")
            pg.wait_for_timeout(6000)
        # 检查输入框可用即可，不做任何会话切换
        for sel in ['div[contenteditable="true"]',
                    'textarea[data-testid="chat_input_input"]']:
            try:
                loc = pg.locator(sel).first
                if loc.count() and loc.is_visible(timeout=2000):
                    return True
            except Exception:
                continue
        return False
    except Exception:
        return False


def do_send(pg, text, skip_check=False):
    """
    发送消息 —— v13 可靠验证版

    关键修正（v12 的教训）：
      消息发出后，服务端拒收会在消息旁显示 errorIcon（红色感叹号 + 重试按钮）
      必须检查这个标志，有则说明失败，不能当成功

    返回 True 仅当：输入框清空 且 消息区出现该文本 且 无错误图标
    """
    try:
        if not skip_check and is_banned(pg):
            return False

        # 等待输入框可用
        ed = None
        deadline = time.time() + 45
        while time.time() < deadline:
            try:
                loc = pg.locator('div[contenteditable="true"]').first
                if loc.count() and loc.is_visible(timeout=1500) and loc.is_enabled(timeout=1500):
                    ed = loc
                    break
            except Exception:
                pass
            time.sleep(1.5)
        if ed is None:
            return False

        # 发送前记录错误图标基线
        try:
            err_before = pg.locator('[class*="errorIcon"]').count()
        except Exception:
            err_before = 0

        # 输入
        ed.click(timeout=8000)
        pg.wait_for_timeout(500)
        pg.keyboard.press("Control+A")
        pg.keyboard.press("Delete")
        pg.wait_for_timeout(300)
        pg.keyboard.type(text, delay=12)
        pg.wait_for_timeout(700)

        try:
            if text[:12] not in (ed.inner_text() or ""):
                return False
        except Exception:
            pass

        # 发送
        pg.keyboard.press("Enter")

        # 验证循环
        for i in range(30):
            pg.wait_for_timeout(1000)

            # 1) 输入框是否已清空
            box_now = ""
            try:
                box_now = (ed.inner_text() or "").strip()
            except Exception:
                pass
            cleared = (text[:12] not in box_now) and len(box_now) < 12
            if not cleared:
                if i == 15:
                    try:
                        pg.keyboard.press("Enter")
                    except Exception:
                        pass
                continue

            # 2) 有无新增错误图标
            try:
                err_now = pg.locator('[class*="errorIcon"]').count()
            except Exception:
                err_now = err_before
            if err_now > err_before:
                # 服务端拒收
                return False

            # 3) 文本是否出现在页面正文（排除输入框）
            try:
                body = pg.inner_text("body")
                if text[:12] in body:
                    import re as _re
                    m = _re.search(r"/chat/(\d{10,})", pg.url or "")
                    if m:
                        NEWCHAT["sid"] = m.group(1)
                    return True
            except Exception:
                pass

        return False
    except Exception:
        return False


def browser_worker():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, headless=True,
            args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu",
                  "--disable-blink-features=AutomationControlled",
                  "--disable-features=IsolateOrigins,site-per-process",
                  "--no-first-run","--no-default-browser-check",
                  "--disable-infobars","--disable-notifications",
                  "--window-size=1200,1000","--lang=zh-CN"],
            viewport={"width":1200,"height":1000},
            screen={"width":1920,"height":1080},
            locale="zh-CN", timezone_id="Asia/Shanghai",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            ignore_default_args=["--enable-automation"],
            extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"})
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        # 注入反检测脚本
        try:
            ctx.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN','zh','en']});
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                window.chrome = {runtime: {}};
            """)
        except Exception:
            pass

        try:
            ctx.set_default_timeout(15000)
            ctx.set_default_navigation_timeout(30000)
        except Exception:
            pass
        PG["page"] = pg
        PG["ctx"] = ctx

        pg.goto("https://www.doubao.com/chat/", timeout=90000, wait_until="domcontentloaded")
        pg.wait_for_timeout(9000)

        st = is_logged_in(pg, ctx)
        if st is True:
            STATE["logged"] = True
            STATE["status"] = "already"
            n = save_cookie(ctx)
            STATE["msg"] = f"已登录（{n} 个 cookie）· 浏览器常驻，自动续期"
        else:
            STATE["logged"] = False
            STATE["status"] = "need_qr"
            STATE["msg"] = "未登录，正在获取二维码…"
            go_login(pg)

        # 常驻循环：每 5 秒检查一次
        loop_i = 0
        while True:
            time.sleep(5)
            loop_i += 1
            # 每 60 秒检查一次登录态（服务端真实校验）
            if loop_i % 12 == 0:
                try:
                    u = pg.url or ""
                    body_now = pg.inner_text("body", timeout=6000)[:400]
                    dropped = ("from_logout" in u) or (
                        "登录" in body_now[:200] and "新对话" not in body_now)
                    if dropped and STATE.get("logged"):
                        STATE["logged"] = False
                        STATE["status"] = "need_qr"
                        STATE["msg"] = "登录已失效（服务端拒绝），请重新扫码"
                        STATE["qr"] = b""
                        try:
                            do_logout(pg, ctx)
                        except Exception:
                            pass
                except Exception:
                    pass
            # --- 处理发送队列 ---
            with SEND_LOCK:
                pending = SEND_QUEUE[:]
                SEND_QUEUE.clear()
            for item in pending:
                try:
                    try:
                        pg.set_default_timeout(15000)
                    except Exception:
                        pass
                    if item.get("action") == "debug":
                        try:
                            info = {"url": pg.url}
                            for sel in ['textarea[data-testid="chat_input_input"]', 'textarea',
                                        'div[contenteditable="true"]']:
                                loc = pg.locator(sel)
                                cnt = loc.count()
                                vis = False
                                enabled = False
                                if cnt:
                                    try:
                                        vis = loc.first.is_visible(timeout=800)
                                        enabled = loc.first.is_enabled(timeout=800)
                                    except Exception:
                                        pass
                                info[sel] = {"count": cnt, "visible": vis, "enabled": enabled}
                            # 当前会话名
                            try:
                                info["page_title"] = pg.title()[:50]
                            except Exception:
                                info["page_title"] = "?"
                            item["result"] = {"ok": True, "info": info}
                        except Exception as e:
                            item["result"] = {"ok": False, "error": str(e)[:80]}
                    elif item.get("action") == "read":
                        try:
                            txt = pg.inner_text("body")[:8000]
                            lines = [x.strip() for x in txt.split("\n") if x.strip()]
                            item["result"] = {"ok": True, "lines": lines[-40:]}
                        except Exception as e:
                            item["result"] = {"ok": False, "error": str(e)[:80]}
                    elif item.get("action") == "listsessions":
                        try:
                            items = pg.evaluate(
                                "() => { const out = []; const seen = {};"
                                " document.querySelectorAll('a[href]').forEach(a => {"
                                " const m = (a.href || '').match(/chat\\/([0-9]+)/);"
                                " if (m && m[1]) {"
                                " const t = ((a.innerText || '') + '').trim().split('\\n')[0];"
                                " if (t && t.length > 1 && t.length < 30 && !seen[m[1]]) {"
                                " seen[m[1]] = 1; out.push({id: m[1], name: t});"
                                " } } }); return out; }")
                            seen = {}
                            NOISE = {"云盘", "云电脑", "新对话", "新工作任务",
                                     "更多", "设置", "项目", "创建新项目",
                                     "插件 · 技能 · 工作台", "定时任务", "主对话"}
                            for it in items:
                                if it["name"] in NOISE:
                                    continue
                                if not str(it["id"]).isdigit():
                                    continue
                                seen[it["id"]] = it
                            item["result"] = {"ok": True, "sessions": list(seen.values())}
                        except Exception as e:
                            item["result"] = {"ok": False, "error": str(e)[:80]}
                    elif item.get("action") == "sendto":
                        try:
                            NEWCHAT["active"] = False
                            tid = item.get("tid", "")
                            if tid in banned_ids():
                                item["result"] = {"ok": False,
                                                  "error": "目标会话已死，禁止发送"}
                                return
                            # 导航到目标会话（同 URL 时强制 reload 确保生效）
                            target = f"https://www.doubao.com/chat/{tid}"
                            if pg.url.rstrip("/") == target.rstrip("/"):
                                pg.reload(timeout=60000, wait_until="domcontentloaded")
                            else:
                                pg.goto(target, timeout=60000, wait_until="domcontentloaded")
                            pg.wait_for_timeout(7000)
                            # 校验导航确实到达目标会话
                            if tid not in (pg.url or ""):
                                item["result"] = {"ok": False,
                                    "error": f"导航未到目标会话(当前={pg.url[:50]})"}
                                return
                            if is_banned(pg):
                                item["result"] = {"ok": False,
                                                  "error": "导航后仍处于禁发会话，已中止"}
                                return
                            ok = do_send(pg, item.get("text", ""), skip_check=True)
                            item["result"] = {"ok": bool(ok)}
                            NEWCHAT["sid"] = tid
                        except Exception as e:
                            item["result"] = {"ok": False, "error": str(e)[:80]}
                    elif item.get("action") == "probe":
                        try:
                            NEWCHAT["active"] = False
                            tid = item.get("tid", "")
                            pg.goto(f"https://www.doubao.com/chat/{tid}",
                                    timeout=60000, wait_until="domcontentloaded")
                            pg.wait_for_timeout(6000)
                            mark = "PING_OK_7719"
                            ok = do_send(pg, f"在沙箱执行 echo {mark}，只回复 {mark}")
                            alive = False
                            if ok:
                                for _ in range(35):
                                    time.sleep(2)
                                    try:
                                        txt = pg.inner_text("body")
                                        tail = txt[-600:]
                                        if mark in txt:
                                            alive = True
                                            break
                                        if "高风险" in tail or "已终止" in tail or "终止本次会话" in tail:
                                            break
                                    except Exception:
                                        pass
                            item["result"] = {"ok": True, "alive": alive}
                        except Exception as e:
                            item["result"] = {"ok": False, "error": str(e)[:80]}
                    elif item.get("action") == "mode":
                        try:
                            # 进入目标会话（模式按钮只在会话内）
                            c = load_keepconf()
                            tgt = c.get("target", "")
                            cur = pg.url or ""
                            if "/chat/" not in cur or cur.rstrip("/") == "https://www.doubao.com/chat":
                                if tgt:
                                    pg.goto(f"https://www.doubao.com/chat/{tgt}",
                                            timeout=60000, wait_until="domcontentloaded")
                                    pg.wait_for_timeout(8000)
                                    if is_banned(pg):
                                        item["result"] = {"ok": False,
                                            "error": "目标会话已死，无法切换模式"}
                                        item["done"] = True

                            if not item.get("done"):
                                # 实测：按钮可能是"对话"或"云电脑"，取出实际位置
                                btn_info = pg.evaluate(
                                    "() => { const o=[]; document.querySelectorAll('button').forEach(b=>{"
                                    " const t=(b.innerText||'').trim(); const r=b.getBoundingClientRect();"
                                    " if(t && r.width>0 && r.height>0) o.push({t:t.slice(0,8),"
                                    " x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)}); }); return o; }")

                                mode_now = "对话"
                                tgt_btn = None
                                for b in btn_info:
                                    if b["t"] == "云电脑":
                                        mode_now = "云电脑"
                                        tgt_btn = b
                                        break
                                    if b["t"] == "对话" and tgt_btn is None:
                                        tgt_btn = b

                                if mode_now != "云电脑" and tgt_btn:
                                    pg.mouse.click(tgt_btn["x"], tgt_btn["y"])
                                    pg.wait_for_timeout(3000)
                                    loc = pg.locator('[role="menuitem"]:has-text("云电脑")')
                                    if loc.count():
                                        loc.last.click(timeout=6000)
                                        pg.wait_for_timeout(4000)
                                    # 复核
                                    after = pg.evaluate(
                                        "() => Array.from(document.querySelectorAll('button'))"
                                        ".map(b=>(b.innerText||'').trim())"
                                        ".filter(t=>t==='对话'||t==='云电脑')")
                                    mode_now = "云电脑" if "云电脑" in after else "对话"

                                item["result"] = {"ok": mode_now == "云电脑", "mode": mode_now}
                        except Exception as e:
                            item["result"] = {"ok": False, "error": str(e)[:80]}
                    elif item.get("action") == "newchat":
                        try:
                            before = pg.url
                            pg.goto("https://www.doubao.com/chat/", timeout=60000,
                                    wait_until="domcontentloaded")
                            pg.wait_for_timeout(8000)
                            clicked = False
                            try:
                                loc = pg.locator("span:text-is('新对话')").first
                                if loc.count():
                                    loc.click(timeout=8000)
                                    clicked = True
                            except Exception:
                                pass
                            pg.wait_for_timeout(4000)
                            NEWCHAT["active"] = True
                            item["result"] = {"ok": True, "clicked": clicked,
                                              "url": pg.url[:70],
                                              "note": "已就绪，发送首条消息后生成会话ID"}
                        except Exception as e:
                            item["result"] = {"ok": False, "error": str(e)[:80]}
                    elif item.get("action") == "getqr":
                        # 先看是否已登录
                        if is_logged_in(pg, ctx) is True:
                            STATE["logged"] = True
                            n = save_cookie(ctx)
                            STATE["msg"] = f"已登录（{n} 个 cookie）"
                            item["result"] = True
                        else:
                            # 重新抓二维码（不刷新页面，只点击登录按钮）
                            go_login(pg)
                            item["result"] = len(STATE["qr"]) > 0
                    elif item.get("action") == "refresh":
                        # 重新抓二维码（不清 cookie，只刷新二维码）
                        go_login(pg)
                        item["result"] = len(STATE["qr"]) > 0
                    elif item.get("action") == "logout":
                        item["result"] = do_logout(pg, ctx)
                    else:
                        item["result"] = do_send(pg, item.get("text", ""))
                except Exception:
                    item["result"] = False

            try:
                # 只读检测，绝不刷新页面（刷新会作废扫码会话）
                now_logged = is_logged_in(pg, ctx) is True
                if now_logged and not STATE["logged"]:
                    STATE["logged"] = True
                    STATE["status"] = "success"
                    n = save_cookie(ctx)
                    STATE["msg"] = f"登录成功（{n} 个 cookie）· 自动续期中"

                    # ===== 登录成功后自动恢复全链路 =====
                    # 1. 解除保活熔断（写状态文件）
                    try:
                        kf = "/root/ka_state.json"
                        ks = json.load(open(kf)) if os.path.exists(kf) else {}
                        ks["stopped"] = False
                        ks["fail_streak"] = 0
                        ks.pop("stopped_at", None)
                        json.dump(ks, open(kf, "w"), ensure_ascii=False, indent=1)
                        logging.info("[auto] 已解除保活熔断")
                    except Exception:
                        pass

                    # 2. 异步触发恢复（不阻塞登录检测循环）
                    def _auto_restore():
                        time.sleep(8)   # 等浏览器稳定
                        try:
                            urllib.request.urlopen(
                                "http://127.0.0.1:18800/restore",
                                data=b"{}", timeout=180)
                        except Exception:
                            pass
                    threading.Thread(target=_auto_restore, daemon=True).start()
                elif not now_logged and STATE["logged"]:
                    STATE["logged"] = False
                    STATE["status"] = "need_qr"
                    STATE["msg"] = "登录已失效，请重新扫码"
                    go_login(pg)
                if STATE["logged"]:
                    save_cookie(ctx)
            except Exception:
                pass


def do_logout(pg, ctx):
    """强制退出登录：清空 cookie，跳转登录页，抓二维码"""
    try:
        ctx.clear_cookies()
        STATE["logged"] = False
        STATE["qr"] = b""
        STATE["msg"] = "正在退出并获取二维码…"
        pg.goto("https://www.doubao.com/login", timeout=60000, wait_until="domcontentloaded")
        pg.wait_for_timeout(8000)
        qr = grab_qr(pg)
        if qr:
            STATE["qr"] = qr
            STATE["status"] = "need_qr"
            STATE["msg"] = "请用豆包 App 扫描二维码"
            return True
        STATE["msg"] = "二维码获取失败，点『重新获取』再试"
        return False
    except Exception as e:
        STATE["msg"] = f"退出失败: {str(e)[:50]}"
        return False


def go_login(pg):
    """进入登录页并抓二维码（实测：需点击顶部登录按钮）"""
    try:
        # 先回首页
        try:
            pg.goto("https://www.doubao.com/chat/", timeout=60000, wait_until="domcontentloaded")
            pg.wait_for_timeout(7000)
        except Exception:
            pass

        # 点顶部"登录"按钮
        clicked = False
        try:
            btns = pg.locator('button:has-text("登录")')
            for i in range(min(btns.count(), 5)):
                el = btns.nth(i)
                box = el.bounding_box()
                if box and box.get("y", 999) < 200 and box.get("width", 999) < 150:
                    el.click(timeout=5000)
                    clicked = True
                    break
        except Exception:
            pass

        if not clicked:
            STATE["msg"] = "未找到登录按钮"
            return

        pg.wait_for_timeout(7000)
        qr = grab_qr(pg)
        if qr:
            STATE["qr"] = qr
            STATE["status"] = "need_qr"
            STATE["msg"] = "请用豆包 App 扫描二维码"
        else:
            STATE["msg"] = "二维码获取失败，请点『重新获取』"
    except Exception as e:
        STATE["msg"] = f"登录流程失败: {str(e)[:50]}"


HTML = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0b0f19">
<link rel="preconnect" href="/">
<title>Moin 控制台</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
:root{--bg:#0b0f19;--card:#121826;--card2:#1a2233;--line:#243044;
--txt:#e8eefc;--dim:#7f8da8;--ok:#3ddc97;--warn:#ffb648;--err:#ff5c7c;
--acc:#4d8dff;--acc2:#7c5cff}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
background:var(--bg);color:var(--txt);line-height:1.6;
padding:env(safe-area-inset-top) 0 env(safe-area-inset-bottom)}

/* 顶部栏 */
.topbar{position:sticky;top:0;z-index:100;background:rgba(11,15,25,.92);
backdrop-filter:blur(14px);border-bottom:1px solid var(--line);
display:flex;align-items:center;gap:12px;padding:13px 16px}
.burger{width:38px;height:38px;border-radius:11px;background:var(--card2);
border:0;display:grid;place-items:center;cursor:pointer;flex:none;transition:.15s}
.burger:active{transform:scale(.94)}
.burger span{display:block;width:17px;height:2px;background:var(--txt);
border-radius:2px;position:relative;transition:.2s}
.burger span:before,.burger span:after{content:"";position:absolute;left:0;
width:17px;height:2px;background:var(--txt);border-radius:2px;transition:.2s}
.burger span:before{top:-5.5px}
.burger span:after{top:5.5px}
.burger.on span{background:transparent}
.burger.on span:before{top:0;transform:rotate(45deg)}
.burger.on span:after{top:0;transform:rotate(-45deg)}
.tb-title{font-size:15.5px;font-weight:700;flex:1}
.tb-sub{font-size:11.5px;color:var(--dim)}

/* 抽屉 */
.drawer{position:fixed;top:0;left:0;bottom:0;width:250px;background:#0e1420;
border-right:1px solid var(--line);z-index:200;transform:translateX(-100%);
transition:transform .25s cubic-bezier(.4,0,.2,1);padding:18px 0;overflow-y:auto}
.drawer.open{transform:translateX(0)}
.mask{position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:150;
opacity:0;pointer-events:none;transition:.25s}
.mask.open{opacity:1;pointer-events:auto}
.d-head{padding:0 20px 16px;border-bottom:1px solid var(--line);margin-bottom:12px}
.d-head .lg{width:42px;height:42px;border-radius:12px;
background:linear-gradient(135deg,var(--acc),var(--acc2));display:grid;
place-items:center;font-size:19px;font-weight:700;margin-bottom:9px}
.d-head .t{font-size:15px;font-weight:700}
.d-head .s{font-size:11.5px;color:var(--dim)}
.d-item{display:flex;align-items:center;gap:13px;padding:13px 20px;
cursor:pointer;transition:.15s;font-size:14px;color:var(--dim)}
.d-item:active{background:var(--card2)}
.d-item.act{background:rgba(77,141,255,.12);color:var(--txt);
border-right:3px solid var(--acc);font-weight:600}
.d-item .ic{width:20px;text-align:center;font-size:15px}

.wrap{max-width:620px;margin:0 auto;padding:20px 16px 50px}
.page{display:none}
.page.act{display:block}

.sec{font-size:11.5px;color:var(--dim);letter-spacing:1px;font-weight:600;
text-transform:uppercase;margin:20px 0 10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px}

/* 状态卡 */
.stat{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}
.stat div{background:var(--card2);border-radius:11px;padding:13px 6px;text-align:center;
  min-width:0;overflow:hidden}
.stat .n{font-size:16px;font-weight:700;font-variant-numeric:tabular-nums;
  max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.stat .l{font-size:10.5px;color:var(--dim);margin-top:3px}
@media (max-width:420px){
  .stat{grid-template-columns:1fr 1fr}
  .stat div:nth-child(2){grid-column:span 2}
}
.n.ok{color:var(--ok)}.n.err{color:var(--err)}.n.warn{color:var(--warn)}
.badge{display:inline-flex;align-items:center;gap:7px;padding:9px 14px;
border-radius:10px;font-size:13px;font-weight:600;margin-top:12px}
.badge.ok{background:rgba(61,220,151,.14);color:var(--ok)}
.badge.err{background:rgba(255,92,124,.14);color:var(--err)}
.dot{width:8px;height:8px;border-radius:50%;background:currentColor;flex:none}

/* 二维码 */
.qrbox{width:100%;max-width:280px;aspect-ratio:1;margin:0 auto;
background:#fff;border-radius:14px;display:grid;place-items:center;
overflow:hidden;position:relative}
.qrbox img{width:100%;height:100%;object-fit:contain}
.qrbox .ph{color:#aaa;font-size:13px}

/* 表单 */
.fld{margin-bottom:14px}
.fld:last-child{margin-bottom:0}
.fld label{display:block;font-size:12.5px;color:var(--dim);margin-bottom:6px;font-weight:500}
.fld input,.fld select{width:100%;padding:12px 13px;border-radius:10px;
border:1px solid var(--line);background:var(--card2);color:var(--txt);
font-size:14px;font-family:inherit;outline:none;transition:.15s}
.fld input:focus,.fld select:focus{border-color:var(--acc)}
.fld .hint{font-size:11px;color:var(--dim);margin-top:4px}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.switch{display:flex;align-items:center;justify-content:space-between;padding:12px 0}
.switch span{font-size:14px;font-weight:600}
.sw{position:relative;width:48px;height:27px;flex:none}
.sw input{opacity:0;width:0;height:0}
.sw .sl{position:absolute;inset:0;background:#2a3547;border-radius:27px;
cursor:pointer;transition:.25s}
.sw .sl:before{content:"";position:absolute;width:21px;height:21px;left:3px;top:3px;
background:#fff;border-radius:50%;transition:.25s}
.sw input:checked + .sl{background:var(--acc)}
.sw input:checked + .sl:before{transform:translateX(21px)}
.btn{width:100%;padding:13px;border:0;border-radius:11px;
background:linear-gradient(135deg,var(--acc),var(--acc2));color:#fff;
font-size:14px;font-weight:600;font-family:inherit;cursor:pointer;
transition:.15s;margin-top:12px}
.btn:active{transform:scale(.985);opacity:.92}
.btn.sec{background:var(--card2);border:1px solid var(--line);color:var(--txt)}
.btn:disabled{opacity:.5}
.msg{padding:11px 14px;border-radius:10px;font-size:13px;margin-top:12px;display:none}
.msg.show{display:block}
.msg.ok{background:rgba(61,220,151,.14);color:var(--ok);border:1px solid rgba(61,220,151,.3)}
.msg.err{background:rgba(255,92,124,.14);color:var(--err);border:1px solid rgba(255,92,124,.3)}
.hist{max-height:240px;overflow:auto}
.hist .it{display:flex;justify-content:space-between;padding:9px 0;
border-bottom:1px solid var(--line);font-size:12.5px}
.hist .it:last-child{border:0}
.hist .t{color:var(--dim);font-size:11.5px}
.hist .f{font-family:ui-monospace,monospace;color:var(--acc)}
.srow{display:flex;align-items:center;gap:8px;padding:9px 0;border-bottom:1px solid var(--line)}
.srow:last-child{border:0}
.srow .sname{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.stbtn,.kpbtn{border:1px solid var(--line);background:var(--card2);color:var(--txt);
  border-radius:8px;padding:6px 10px;font-size:11.5px;font-family:inherit;flex:none;cursor:pointer}
.stbtn.on{color:var(--ok);border-color:rgba(61,220,151,.4)}
.stbtn.off{color:var(--err);border-color:rgba(255,92,124,.4)}
.kpbtn.on{background:rgba(77,141,255,.2);border-color:var(--acc);color:var(--acc);font-weight:600}
.kpbtn:disabled{opacity:.35;cursor:not-allowed}

/* ===== 移动端全面适配 ===== */
@media (max-width: 480px) {
  .wrap{padding:16px 12px 40px}
  .topbar{padding:11px 12px}
  .tb-title{font-size:14.5px}
  .tb-sub{font-size:11px}

  .stat{grid-template-columns:1fr !important;gap:8px}
  .stat div{padding:14px 12px;display:flex;align-items:center;
    justify-content:space-between;text-align:left}
  .stat .n{font-size:17px;order:2}
  .stat .l{font-size:12px;margin-top:0;order:1}

  .card{padding:14px;border-radius:12px}
  .fld input,.fld select{padding:12px;font-size:15px}
  .btn{padding:14px;font-size:14.5px}
  .sec{font-size:11px;margin:18px 0 8px}

  .srow{flex-wrap:wrap;gap:6px}
  .srow .sname{flex:1 1 100%;margin-bottom:4px}
  .stbtn,.kpbtn{padding:7px 12px;font-size:12px;flex:1}

  .qrbox{max-width:240px}
  .d-item{padding:14px 18px;font-size:14px}
  .hist .it{flex-direction:column;align-items:flex-start;gap:3px}
  .row{flex-wrap:wrap;gap:4px}
  .row .v{word-break:break-all;text-align:right;max-width:60%}
}
@media (max-width: 360px) {
  .stat .n{font-size:15px}
  .btn{padding:12px;font-size:14px}
}
</style></head>
<body>

<div class="topbar">
  <button class="burger" id="bg"><span></span></button>
  <div style="flex:1">
    <div class="tb-title" id="tbT">扫码登录</div>
    <div class="tb-sub" id="tbS">Moin 控制台</div>
  </div>
</div>

<div class="mask" id="mk"></div>
<div class="drawer" id="dw">
  <div class="d-head">
    <div class="lg">M</div>
    <div class="t">Moin 控制台</div>
    <div class="s">豆包沙箱 · 统一管理</div>
  </div>
  <div class="d-item act" data-p="login"><span class="ic">▣</span>扫码登录</div>
  <div class="d-item" data-p="ctrl"><span class="ic">⌘</span>沙箱控制</div>
  <div class="d-item" data-p="keep"><span class="ic">♡</span>保活控制</div>
  <div class="d-item" data-p="mail"><span class="ic">✉</span>邮件配置</div>
  <div class="d-item" data-p="status"><span class="ic">◈</span>状态监控</div>
</div>

<div class="wrap">

  <!-- 扫码登录 -->
  <div class="page act" id="p-login">
    <div class="card" style="text-align:center">
      <div style="font-size:16px;font-weight:700;margin-bottom:4px">豆包扫码登录</div>
      <div style="font-size:12px;color:var(--dim);margin-bottom:18px">用豆包 App 扫描二维码</div>
      <div class="qrbox" id="qrbox"><div class="ph">加载中…</div></div>
      <div class="badge" id="loginBadge" style="justify-content:center">
        <span class="dot"></span><span id="loginMsg">检查中…</span>
      </div>
      <button class="btn" id="getQr" style="margin-top:16px">获取二维码 / 重新登录</button>
    </div>
  </div>

  <!-- 沙箱控制 -->
  <div class="page" id="p-ctrl">
    <div class="sec">模式与会话</div>
    <div class="card" style="display:flex;gap:9px">
      <button class="btn sec" id="bMode" style="margin:0;flex:1">切云电脑</button>
      <button class="btn sec" id="bNew" style="margin:0;flex:1">新会话</button>
    </div>

    <div class="sec">发送指令</div>
    <div class="card">
      <textarea id="cmd" rows="3" style="width:100%;padding:12px 13px;border-radius:10px;
        border:1px solid var(--line);background:var(--card2);color:var(--txt);
        font-size:14px;font-family:inherit;outline:none;resize:vertical"
        placeholder="输入给豆包的指令（云电脑模式下会真实执行）"></textarea>
      <button class="btn" id="bSend">发送</button>
      <div class="msg" id="mCmd"></div>
    </div>

    <div class="sec">会话最新内容</div>
    <div class="card">
      <div id="readout" style="max-height:260px;overflow:auto;font-size:12.5px;
        line-height:1.8;color:var(--dim);white-space:pre-wrap">点击下方刷新读取</div>
      <button class="btn sec" id="bRead" style="margin-top:10px">读取会话</button>
    </div>

    <div class="sec">沙箱隧道</div>
    <div class="card">
      <div class="stat">
        <div><div class="n" id="t-state">—</div><div class="l">隧道状态</div></div>
        <div><div class="n" id="t-rtt">—</div><div class="l">延迟</div></div>
        <div><div class="n" id="t-up">—</div><div class="l">运行</div></div>
      </div>
      <button class="btn sec" id="bPing" style="margin-top:12px">探测沙箱 (/ping)</button>
      <div class="msg" id="mPing"></div>
    </div>
  </div>

  <!-- 保活控制 -->
  <div class="page" id="p-keep">
    <div class="sec">保活服务</div>
    <div class="card">
      <div class="stat">
        <div><div class="n" id="k-state">—</div><div class="l">状态</div></div>
        <div><div class="n" id="k-interval">—</div><div class="l">检测间隔</div></div>
        <div><div class="n" id="k-count">—</div><div class="l">已执行</div></div>
      </div>
      <div style="display:flex;gap:9px;margin-top:12px">
        <button class="btn" id="kStart" style="margin:0;flex:1">启动</button>
        <button class="btn sec" id="kStop" style="margin:0;flex:1">停止</button>
      </div>
      <div class="msg" id="mKeep"></div>
    </div>

    <div class="sec">隧道</div>
    <div class="card">
      <div class="stat">
        <div><div class="n" id="c-state">—</div><div class="l">CF域名</div></div>
        <div><div class="n" id="f-state">—</div><div class="l">frp隧道</div></div>
        <div><div class="n" id="s-state">—</div><div class="l">沙箱</div></div>
      </div>
      <button class="btn sec" id="bRestore" style="margin-top:12px">一键恢复隧道+保活</button>
      <div class="msg" id="mRestore"></div>
    </div>

    <div class="sec">保活目标</div>
    <div class="card">
      <div class="fld">
        <label>会话名称</label>
        <input id="keepName" placeholder="输入豆包会话名称，如：运行脚本恢复服务" autocomplete="off">
        <div class="hint">填写你在豆包里用于保活的那个会话的完整名称</div>
      </div>
      <button class="btn" id="keepSave">保存并启用</button>
      <div style="display:flex;gap:9px;margin-top:10px">
        <button class="btn sec" id="keepOn" style="margin:0;flex:1">开启保活</button>
        <button class="btn sec" id="keepOff" style="margin:0;flex:1">关闭保活</button>
      </div>
      <div class="msg" id="mKeepName"></div>
    </div>

    <div class="sec">保活日志</div>
    <div class="card">
      <div id="kLog" style="max-height:240px;overflow:auto;font-size:11.5px;
        line-height:1.7;color:var(--dim);white-space:pre-wrap;font-family:ui-monospace,monospace">—</div>
      <button class="btn sec" id="kRefresh" style="margin-top:10px">刷新日志</button>
    </div>
  </div>

  <!-- 邮件配置 -->
  <div class="page" id="p-mail">
    <div class="sec">邮件通知</div>
    <div class="card">
      <div class="switch">
        <span>启用邮件告警</span>
        <label class="sw"><input type="checkbox" id="en"><span class="sl"></span></label>
      </div>
      <div class="fld"><label>邮箱服务商</label>
        <select id="preset">
          <option value="qq">QQ 邮箱</option>
          <option value="163">163 邮箱</option>
          <option value="gmail">Gmail</option>
          <option value="outlook">Outlook</option>
          <option value="aliyun">阿里云邮箱</option>
          <option value="custom">自定义</option>
        </select>
      </div>
      <div class="row2">
        <div class="fld"><label>SMTP 服务器</label><input id="host" placeholder="smtp.qq.com"></div>
        <div class="fld"><label>端口</label><input id="port" type="number" placeholder="465"></div>
      </div>
      <div class="fld"><label>发件邮箱</label><input id="user" placeholder="你的邮箱@qq.com" autocomplete="off"></div>
      <div class="fld"><label>授权码 / 密码</label>
        <input id="pass" type="password" placeholder="SMTP 授权码" autocomplete="off">
        <div class="hint">QQ/163 需在邮箱设置开启 SMTP 并获取授权码（非登录密码）</div>
      </div>
      <div class="fld"><label>收件邮箱</label><input id="to" placeholder="接收告警的邮箱" autocomplete="off"></div>
      <button class="btn" id="save">保存配置</button>
      <button class="btn sec" id="test">发送测试邮件</button>
      <div class="msg" id="m1"></div>
    </div>
  </div>

  <!-- 状态监控 -->
  <div class="page" id="p-status">
    <div class="sec">Cookie 状态</div>
    <div class="card">
      <div class="stat">
        <div><div class="n" id="s-count">—</div><div class="l">Cookie 数</div></div>
        <div><div class="n" id="s-fp">—</div><div class="l">指纹</div></div>
        <div><div class="n" id="s-renew">—</div><div class="l">续期次数</div></div>
      </div>
      <div class="badge" id="stBadge"><span class="dot"></span><span id="stMsg">加载中…</span></div>
    </div>

    <div class="sec">续期历史</div>
    <div class="card">
      <div class="hist" id="hist"><div style="color:var(--dim);font-size:13px">暂无记录</div></div>
    </div>
  </div>

</div>

<script>
const $ = id => document.getElementById(id);
function bindSafeChange(id, fn){
  const el = $(id);
  if (el) el.onchange = fn;
}
function bindSafe(id, fn){
  const el = $(id);
  if (el) el.onclick = fn;
  return el;
}

// 抽屉
const bg = $('bg'), dw = $('dw'), mk = $('mk');
bg.onclick = () => { dw.classList.toggle('open'); mk.classList.toggle('open'); bg.classList.toggle('on'); };
mk.onclick = () => { dw.classList.remove('open'); mk.classList.remove('open'); bg.classList.remove('on'); };

const TITLES = {login: ['扫码登录','豆包账号'], ctrl: ['沙箱控制','指令与隧道'], keep: ['保活控制','沙箱唤醒'], mail: ['邮件配置','告警通知'], status: ['状态监控','Cookie 健康']};
document.querySelectorAll('.d-item').forEach(it => {
  it.onclick = () => {
    const p = it.dataset.p;
    document.querySelectorAll('.d-item').forEach(x => x.classList.remove('act'));
    document.querySelectorAll('.page').forEach(x => x.classList.remove('act'));
    it.classList.add('act');
    $('p-' + p).classList.add('act');
    $('tbT').textContent = TITLES[p][0];
    $('tbS').textContent = TITLES[p][1];
    dw.classList.remove('open'); mk.classList.remove('open'); bg.classList.remove('on');
    window.scrollTo(0,0);
  };
});

// 登录状态
let lastQrLen = -1;
async function checkLogin() {
  try {
    const r = await fetch('/state');
    const d = await r.json();
    const badge = $('loginBadge'), msg = $('loginMsg');
    msg.textContent = d.msg;
    badge.className = 'badge ' + (d.logged ? 'ok' : 'err');
    if (d.logged) {
      $('qrbox').innerHTML = '<div class="ph" style="color:#3ddc97;font-size:15px;font-weight:600">✓ 已登录</div>';
      lastQrLen = d.qr_len;
    } else if (d.qr_len > 0) {
      if (d.qr_len !== lastQrLen) {
        lastQrLen = d.qr_len;
        $('qrbox').innerHTML = '<img src="/qr?' + Date.now() + '" alt="二维码">';
      }
    } else {
      $('qrbox').innerHTML = '<div class="ph">等待二维码…</div>';
    }
  } catch(e) {}
}

bindSafe('getQr', async () => {
  const btn = $('getQr');
  btn.disabled = true;
  btn.textContent = '正在获取二维码…';
  $('qrbox').innerHTML = '<div class="ph">获取中…</div>';
  lastQrLen = -1;
  try {
    const r = await fetch('/getqr', {method:'POST'});
    const d = await r.json();
    if (!d.ok) {
      $('qrbox').innerHTML = '<div class="ph" style="color:#ff5c7c">' + (d.error || '获取失败') + '</div>';
    }
  } catch(e) {
    $('qrbox').innerHTML = '<div class="ph" style="color:#ff5c7c">请求失败</div>';
  }
  btn.disabled = false;
  btn.textContent = '获取二维码 / 重新登录';
  setTimeout(checkLogin, 1200);
});

// 邮件配置
const PRESETS = {
  qq:{host:'smtp.qq.com',port:465}, '163':{host:'smtp.163.com',port:465},
  gmail:{host:'smtp.gmail.com',port:587}, outlook:{host:'smtp.office365.com',port:587},
  aliyun:{host:'smtp.mxhichina.com',port:465}, custom:{host:'',port:465}
};
bindSafeChange('preset', () => {
  const p = PRESETS[$('preset').value];
  if (p) { $('host').value = p.host; $('port').value = p.port; }
});

async function loadConf() {
  try {
    const r = await fetch('/api/conf');
    const d = await r.json();
    const e = d.email || {};
    $('en').checked = !!e.enabled;
    $('host').value = e.smtp_host || 'smtp.qq.com';
    $('port').value = e.smtp_port || 465;
    $('user').value = e.smtp_user || '';
    $('pass').value = e.smtp_pass || '';
    $('to').value = e.to || '';
    for (const [k,v] of Object.entries(PRESETS)) {
      if (v.host === e.smtp_host) { $('preset').value = k; break; }
    }
  } catch(e) {}
}

function show(el, txt, ok) {
  el.textContent = txt;
  el.className = 'msg show ' + (ok ? 'ok' : 'err');
  setTimeout(() => el.classList.remove('show'), 5000);
}

bindSafe('save', async () => {
  const body = {email:{
    enabled: $('en').checked,
    smtp_host: $('host').value.trim(),
    smtp_port: parseInt($('port').value) || 465,
    smtp_user: $('user').value.trim(),
    smtp_pass: $('pass').value,
    to: $('to').value.trim()
  }};
  const r = await fetch('/api/conf', {method:'POST', body: JSON.stringify(body)});
  const d = await r.json();
  show($('m1'), d.ok ? '✓ 配置已保存' : '✗ ' + (d.error||'失败'), d.ok);
});

bindSafe('test', async () => {
  $('test').disabled = true; $('test').textContent = '发送中…';
  const r = await fetch('/api/test', {method:'POST'});
  const d = await r.json();
  $('test').disabled = false; $('test').textContent = '发送测试邮件';
  show($('m1'), d.ok ? '✓ 已发送，请查收' : '✗ ' + (d.error||'失败'), d.ok);
});

// 状态
async function loadStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    $('s-count').textContent = d.cookie_count || 0;
    $('s-fp').textContent = d.fp ? d.fp.slice(0,8) : '—';
    $('s-renew').textContent = (d.history||[]).length;
    $('s-count').className = 'n ' + (d.ok ? 'ok' : 'err');
    const b = $('stBadge');
    b.className = 'badge ' + (d.ok ? 'ok' : 'err');
    $('stMsg').textContent = d.ok ? '登录正常' : ('异常: ' + (d.reason||''));
    if (d.history && d.history.length) {
      $('hist').innerHTML = d.history.slice().reverse().map(h =>
        `<div class="it"><span class="f">${h.fp}</span><span class="t">${(h.time||'').replace('T',' ').slice(0,19)}</span></div>`
      ).join('');
    }
  } catch(e) {}
}

// 沙箱控制
bindSafe('bMode', async () => {
  const b = $('bMode'); b.disabled = true; b.textContent = '切换中…';
  try {
    const r = await fetch('/mode', {method:'POST'});
    const d = await r.json();
    show($('mCmd'), d.ok ? '✓ ' + (d.msg||'已切换') : '✗ ' + (d.error||'失败'), d.ok);
  } catch(e) { show($('mCmd'), '✗ 请求失败', false); }
  b.disabled = false; b.textContent = '切云电脑';
});

bindSafe('bNew', async () => {
  const b = $('bNew'); b.disabled = true; b.textContent = '创建中…';
  try {
    const r = await fetch('/newchat', {method:'POST'});
    const d = await r.json();
    show($('mCmd'), d.ok ? '✓ 新会话已创建' : '✗ ' + (d.error||'失败'), d.ok);
  } catch(e) { show($('mCmd'), '✗ 请求失败', false); }
  b.disabled = false; b.textContent = '新会话';
});

bindSafe('bSend', async () => {
  const t = $('cmd').value.trim();
  if (!t) { show($('mCmd'), '请输入指令', false); return; }
  const b = $('bSend'); b.disabled = true; b.textContent = '发送中（豆包执行需时）…';
  try {
    const r = await fetch('/send', {method:'POST',
      headers:{'Content-Type':'application/json'}, body: JSON.stringify({text:t})});
    const d = await r.json();
    show($('mCmd'), d.ok ? '✓ 已发送，稍后点"读取会话"看结果' : '✗ ' + (d.error||'失败'), d.ok);
    if (d.ok) $('cmd').value = '';
  } catch(e) { show($('mCmd'), '✗ 请求失败', false); }
  b.disabled = false; b.textContent = '发送';
});

bindSafe('bRead', async () => {
  const b = $('bRead'); b.disabled = true; b.textContent = '读取中…';
  try {
    const r = await fetch('/read', {method:'POST'});
    const d = await r.json();
    if (d.ok) {
      $('readout').textContent = d.lines.slice(-30).join('\n') || '（空）';
    } else { $('readout').textContent = '读取失败: ' + (d.error||''); }
  } catch(e) { $('readout').textContent = '请求失败'; }
  b.disabled = false; b.textContent = '读取会话';
});

bindSafe('bPing', async () => {
  const b = $('bPing'); b.disabled = true;
  const t0 = performance.now();
  try {
    const r = await fetch('/sandboxping', {method:'POST'});
    const d = await r.json();
    const ms = Math.round(performance.now() - t0);
    $('t-state').textContent = d.ok ? '在线' : '离线';
    $('t-state').className = 'n ' + (d.ok ? 'ok' : 'err');
    $('t-rtt').textContent = d.ok ? ms + 'ms' : '—';
    $('t-up').textContent = d.up != null ? d.up + 's' : '—';
    show($('mPing'), d.ok ? '✓ 沙箱在线' : '✗ ' + (d.error||'离线'), d.ok);
  } catch(e) { show($('mPing'), '✗ 请求失败', false); }
  b.disabled = false;
});

// 保活控制
async function loadKeep() {
  try {
    const r = await fetch('/keepalive');
    const d = await r.json();
    // 回显目标会话名称
    try {
      const rc = await fetch('/sessions');
      const dc = await rc.json();
      const tgt = dc.target || '';
      if (tgt && dc.sessions && dc.sessions[tgt]) {
        const el = $('keepName');
        if (el && !el.value) el.value = dc.sessions[tgt].name || '';
      }
    } catch(e) {}
    $('k-state').textContent = d.state === 'active' ? '运行中' : (d.state === 'inactive' ? '已停止' : d.state);
    $('k-state').className = 'n ' + (d.state === 'active' ? 'ok' : 'err');
    $('k-interval').textContent = d.interval || '—';
    $('k-count').textContent = d.count || '—';
  } catch(e) {}
}
// 保存会话名称并启用
bindSafe('keepSave', async () => {
  const name = ($('keepName').value || '').trim();
  if (!name) { show($('mKeepName'), '请输入会话名称', false); return; }
  const b = $('keepSave'); b.disabled = true; b.textContent = '查找中…';
  try {
    // 先刷新列表找这个名称
    const r1 = await fetch('/sessions', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({op:'refresh'})});
    const d1 = await r1.json();
    if (!d1.ok) { show($('mKeepName'), '📋 读取会话列表失败', false); }
    else {
      let found = null;
      for (const [sid, v] of Object.entries(d1.sessions || {})) {
        if ((v.name || '').trim() === name) { found = sid; break; }
      }
      if (!found) {
        const names = Object.values(d1.sessions||{}).map(v=>v.name).join('、');
        show($('mKeepName'), '未找到「' + name + '」，现有：' + names, false);
      } else {
        // 设为保活目标并启用
        const r2 = await fetch('/sessions', {method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({op:'toggle', id: found, alive: true})});
        const d2 = await r2.json();
        if (d2.ok) {
          await fetch('/keepalive', {method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({action:'start'})});
          show($('mKeepName'), '✅ 已设置「' + name + '」为保活目标并开启', true);
          setTimeout(loadKeep, 1500);
        } else {
          show($('mKeepName'), '❌ ' + (d2.error||'设置失败'), false);
        }
      }
    }
  } catch(e) { show($('mKeepName'), '❌ 请求失败', false); }
  b.disabled = false; b.textContent = '保存并启用';
});

bindSafe('keepOn', async () => {
  const r = await fetch('/keepalive', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({action:'start'})});
  const d = await r.json();
  show($('mKeepName'), d.ok ? '✅ 保活已开启' : '❌ ' + (d.error||''), d.ok);
  setTimeout(loadKeep, 1500);
});

bindSafe('keepOff', async () => {
  const r = await fetch('/keepalive', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({action:'stop'})});
  const d = await r.json();
  show($('mKeepName'), d.ok ? '⏸ 保活已关闭' : '❌ ' + (d.error||''), d.ok);
  setTimeout(loadKeep, 1500);
});

bindSafe('kStart', async () => {
  const r = await fetch('/keepalive', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'start'})});
  const d = await r.json();
  show($('mKeep'), d.ok ? '✓ 已启动' : '✗ ' + (d.error||'失败'), d.ok);
  setTimeout(loadKeep, 1500);
});
bindSafe('kStop', async () => {
  const r = await fetch('/keepalive', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'stop'})});
  const d = await r.json();
  show($('mKeep'), d.ok ? '✓ 已停止' : '✗ ' + (d.error||'失败'), d.ok);
  setTimeout(loadKeep, 1500);
});
bindSafe('kRefresh', async () => {
  const r = await fetch('/keepalive', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'log'})});
  const d = await r.json();
  $('kLog').textContent = d.log || '（无日志）';
});
bindSafe('bRestore', async () => {
  const b = $('bRestore'); b.disabled = true; b.textContent = '恢复中（约1-3分钟）…';
  try {
    const r = await fetch('/restore', {method:'POST'});
    const d = await r.json();
    show($('mRestore'), d.ok ? '✓ ' + (d.out||'完成').replace('\n',' | ') : '✗ ' + (d.error||'失败'), d.ok);
    setTimeout(loadTunnels, 2000);
  } catch(e) { show($('mRestore'), '✗ 请求失败', false); }
  b.disabled = false; b.textContent = '一键恢复隧道+保活';
});
async function loadTunnels() {
  try {
    const r = await fetch('/tunnels');
    const d = await r.json();
    if (!d.ok) return;
    $('c-state').textContent = d.cf ? '通' : '断';
    $('c-state').className = 'n ' + (d.cf ? 'ok' : 'err');
    $('f-state').textContent = d.frp ? '通' : '断';
    $('f-state').className = 'n ' + (d.frp ? 'ok' : 'err');
    $('s-state').textContent = d.frp ? '在线' : '离线';
    $('s-state').className = 'n ' + (d.frp ? 'ok' : 'err');
  } catch(e) {}
}

// 会话管理
function renderSessions(c) {
  const el = $('sessList');
  const ids = Object.keys(c.sessions || {});
  if (!ids.length) { el.innerHTML = '<div style="color:var(--dim)">列表为空，先点刷新</div>'; return; }
  el.innerHTML = ids.map(id => {
    const s = c.sessions[id];
    const aliveBtn = `<button class="stbtn ${s.alive ? 'on' : 'off'}" onclick="sessAlive('${id}')">${s.alive ? '● 存活' : '✕ 已死'}</button>`;
    const keepBtn = `<button class="kpbtn ${s.keep ? 'on' : ''}" ${s.alive ? '' : 'disabled'} onclick="sessKeep('${id}')">${s.keep ? '正在保活' : '保活'}</button>`;
    return `<div class="srow"><div class="sname">${s.name || id}</div>${aliveBtn}${keepBtn}</div>`;
  }).join('');
}
window.sessAlive = async (id) => {
  const r = await fetch('/sessions', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({op:'status', id, alive: !(currentConf.sessions[id]||{}).alive})});
  const d = await r.json();
  if (d.ok) { currentConf = d; renderSessions(d); }
};
window.sessKeep = async (id) => {
  const s = currentConf.sessions[id] || {};
  if (!s.keep) {
    const r = await fetch('/sessions', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({op:'toggle', id, alive: s.alive})});
    const d = await r.json();
    if (!d.ok) { alert(d.error || '失败'); return; }
    currentConf = d;
  } else {
    // 取消保活：alive 保持，keep 置空 —— 通过 toggle 到自身即可覆盖；提供空选：
    const r = await fetch('/sessions', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({op:'toggle', id:'', alive:true})});
    const d = await r.json();
    if (d.ok) currentConf = d;
  }
  renderSessions(currentConf);
};
let currentConf = {sessions:{}};
loadConf();
checkLogin();
loadStatus();
loadKeep();
loadTunnels();
setInterval(loadKeep, 10000);
setInterval(loadTunnels, 15000);
setInterval(checkLogin, 3000);
setInterval(loadStatus, 8000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/", "/index.html"):
            return self._send(200, HTML, "text/html")
        if p.startswith("/qr"):
            qr = STATE["qr"]
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(qr)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(qr)
            except Exception:
                pass
            return
        if p == "/state":
            return self._send(200, {
                "msg": STATE["msg"], "logged": STATE["logged"],
                "status": STATE["status"], "qr_len": len(STATE["qr"])})
        if p == "/sessions":
            if self.command == "GET":
                c = load_keepconf()
                return self._send(200, {"ok": True, **c})
            # POST: 刷新列表/改状态/设目标/探测
            try:
                data = json.loads(body) if body else {}
            except Exception:
                data = {}
            act = data.get("op", "")
            c = load_keepconf()
            if act == "refresh":
                item = {"action": "listsessions", "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                for _ in range(120):     # 最长等 90 秒
                    if item["result"] is not None:
                        break
                    time.sleep(0.75)
                if not (item["result"] or {}).get("ok"):
                    return self._send(200, {"ok": False,
                        "error": (item["result"] or {}).get("error", "读取失败")})
                cur = {it["id"]: it["name"] for it in item["result"]["sessions"]}
                merged = {}
                for sid, name in cur.items():
                    old = c["sessions"].get(sid, {})
                    merged[sid] = {"name": name,
                                   "alive": old.get("alive", None),
                                   "keep": old.get("keep", False)}
                for sid in list(c["sessions"]):
                    if sid not in merged:
                        # 只保留数字 id 的历史记录，清掉噪音
                        if str(sid).isdigit():
                            merged[sid] = {**c["sessions"][sid], "alive": False}
                c["sessions"] = merged
                if c.get("target") and c["target"] not in merged:
                    c["target"] = ""
                save_keepconf(c)
                return self._send(200, {"ok": True, **c})
            if act == "status":
                sid = data.get("id", "")
                if sid in c["sessions"]:
                    c["sessions"][sid]["alive"] = data.get("alive")
                    save_keepconf(c)
                return self._send(200, {"ok": True, **c})
            if act == "toggle":
                sid = data.get("id", "")
                if not sid:
                    for k in c["sessions"]:
                        c["sessions"][k]["keep"] = False
                    c["target"] = ""
                    save_keepconf(c)
                    return self._send(200, {"ok": True, **c})
                if sid not in c["sessions"]:
                    return self._send(200, {"ok": False, "error": "会话不存在"})
                if not data.get("alive", False):
                    return self._send(200, {"ok": False, "error": "已死会话不能保活"})
                for k in c["sessions"]:
                    c["sessions"][k]["keep"] = (k == sid)
                c["target"] = sid
                save_keepconf(c)
                return self._send(200, {"ok": True, **c})
            if act == "probe":
                sid = data.get("id", "")
                item = {"action": "probe", "tid": sid, "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                for _ in range(150):
                    if item["result"] is not None:
                        break
                    time.sleep(1)
                r = item["result"] or {"ok": False, "error": "超时"}
                if r.get("ok"):
                    if sid in c["sessions"]:
                        c["sessions"][sid]["alive"] = r.get("alive")
                        save_keepconf(c)
                    r["conf"] = c
                return self._send(200, r)
            return self._send(200, {"ok": False, "error": "未知操作"})

        if p == "/api/status":
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location("hc", "/root/healthcheck.py")
                hc = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(hc)
                ck = hc.check_cookie()
                st = hc.load_state()
                return self._send(200, {
                    "ok": ck["ok"],
                    "reason": ", ".join(ck.get("missing", [])),
                    "cookie_count": ck.get("count", 0),
                    "fp": ck.get("fp", ""),
                    "history": st.get("history", [])})
            except Exception as e:
                return self._send(200, {"ok": False, "reason": str(e)[:60],
                                        "cookie_count": 0, "fp": "", "history": []})

        if p == "/tunnels":
            try:
                import subprocess
                r1 = subprocess.run(["curl","-s","-m","6","-o","/dev/null","-w","%{http_code}",
                                     (f"https://{CF_DOMAIN}/ping" if CF_DOMAIN else "http://127.0.0.1:18800/ping")],
                                    capture_output=True, text=True, timeout=10)
                cf = r1.stdout.strip() == "200"
                r2 = subprocess.run(["curl","-s","-m","5","http://127.0.0.1:17800/ping"],
                                    capture_output=True, text=True, timeout=8)
                frp = r2.returncode == 0 and "ok" in r2.stdout
                return self._send(200, {"ok": True, "cf": cf, "frp": frp})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        if p == "/keepalive":
            try:
                import subprocess
                st = subprocess.run(["systemctl","is-active","doubao-keepalive"],
                                    capture_output=True, text=True, timeout=8)
                state = st.stdout.strip() or "unknown"

                count, interval, last, mode = "0", "1s", "", "监测中"
                try:
                    log_tail = subprocess.run(["tail","-40","/root/keepalive_daemon.log"],
                                              capture_output=True, text=True, timeout=8).stdout
                    lines = [l for l in log_tail.splitlines() if l.strip()]
                    # 最后一条有效事件
                    for line in reversed(lines):
                        if "任务#" in line:
                            last = line[:19]; mode = "任务保活"; break
                        if "拉起指令" in line:
                            last = line[:19]; mode = "隧道恢复"; break
                        if "隧道断开" in line:
                            last = line[:19]; mode = "检测异常"; break
                    # 计数（从启动算）
                    import re as _re
                    nums = _re.findall(r"\[(\d+)\]", log_tail)
                    if nums:
                        count = nums[-1]
                    interval = "1s 检测 / 2-2.5min 任务"
                except Exception:
                    pass

                return self._send(200, {"ok": True, "state": state,
                                        "count": count, "interval": interval,
                                        "last": last, "mode": mode})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        if p == "/sessions":
            if self.command == "GET":
                c = load_keepconf()
                return self._send(200, {"ok": True, **c})
            # POST: 刷新列表/改状态/设目标/探测
            try:
                data = json.loads(body) if body else {}
            except Exception:
                data = {}
            act = data.get("op", "")
            c = load_keepconf()
            if act == "refresh":
                item = {"action": "listsessions", "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                for _ in range(120):     # 最长等 90 秒
                    if item["result"] is not None:
                        break
                    time.sleep(0.75)
                if not (item["result"] or {}).get("ok"):
                    return self._send(200, {"ok": False,
                        "error": (item["result"] or {}).get("error", "读取失败")})
                cur = {it["id"]: it["name"] for it in item["result"]["sessions"]}
                merged = {}
                for sid, name in cur.items():
                    old = c["sessions"].get(sid, {})
                    merged[sid] = {"name": name,
                                   "alive": old.get("alive", None),
                                   "keep": old.get("keep", False)}
                for sid in list(c["sessions"]):
                    if sid not in merged:
                        # 只保留数字 id 的历史记录，清掉噪音
                        if str(sid).isdigit():
                            merged[sid] = {**c["sessions"][sid], "alive": False}
                c["sessions"] = merged
                if c.get("target") and c["target"] not in merged:
                    c["target"] = ""
                save_keepconf(c)
                return self._send(200, {"ok": True, **c})
            if act == "status":
                sid = data.get("id", "")
                if sid in c["sessions"]:
                    c["sessions"][sid]["alive"] = data.get("alive")
                    save_keepconf(c)
                return self._send(200, {"ok": True, **c})
            if act == "toggle":
                sid = data.get("id", "")
                if not sid:
                    for k in c["sessions"]:
                        c["sessions"][k]["keep"] = False
                    c["target"] = ""
                    save_keepconf(c)
                    return self._send(200, {"ok": True, **c})
                if sid not in c["sessions"]:
                    return self._send(200, {"ok": False, "error": "会话不存在"})
                if not data.get("alive", False):
                    return self._send(200, {"ok": False, "error": "已死会话不能保活"})
                for k in c["sessions"]:
                    c["sessions"][k]["keep"] = (k == sid)
                c["target"] = sid
                save_keepconf(c)
                return self._send(200, {"ok": True, **c})
            if act == "probe":
                sid = data.get("id", "")
                item = {"action": "probe", "tid": sid, "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                for _ in range(150):
                    if item["result"] is not None:
                        break
                    time.sleep(1)
                r = item["result"] or {"ok": False, "error": "超时"}
                if r.get("ok"):
                    if sid in c["sessions"]:
                        c["sessions"][sid]["alive"] = r.get("alive")
                        save_keepconf(c)
                    r["conf"] = c
                return self._send(200, r)
            return self._send(200, {"ok": False, "error": "未知操作"})

        if p == "/api/status":
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location("hc", "/root/healthcheck.py")
                hc = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(hc)
                ck = hc.check_cookie()
                st = hc.load_state()
                return self._send(200, {
                    "ok": ck["ok"],
                    "reason": ", ".join(ck.get("missing", [])),
                    "cookie_count": ck.get("count", 0),
                    "fp": ck.get("fp", ""),
                    "history": st.get("history", [])})
            except Exception as e:
                return self._send(200, {"ok": False, "reason": str(e)[:60],
                                        "cookie_count": 0, "fp": "", "history": []})

        if p == "/tunnels":
            try:
                import subprocess
                r1 = subprocess.run(["curl","-s","-m","6","-o","/dev/null","-w","%{http_code}",
                                     (f"https://{CF_DOMAIN}/ping" if CF_DOMAIN else "http://127.0.0.1:18800/ping")],
                                    capture_output=True, text=True, timeout=10)
                cf = r1.stdout.strip() == "200"
                r2 = subprocess.run(["curl","-s","-m","5","http://127.0.0.1:17800/ping"],
                                    capture_output=True, text=True, timeout=8)
                frp = r2.returncode == 0 and "ok" in r2.stdout
                return self._send(200, {"ok": True, "cf": cf, "frp": frp})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        if p == "/keepalive":
            try:
                import subprocess
                st = subprocess.run(["systemctl","is-active","doubao-keepalive"],
                                    capture_output=True, text=True, timeout=8)
                state = st.stdout.strip() or "unknown"
                cnt, interval, last = "?", "?", ""
                try:
                    log_tail = subprocess.run(["tail","-5","/root/keepalive_daemon.log"],
                                              capture_output=True, text=True, timeout=8).stdout
                    for line in log_tail.splitlines():
                        if "] [" in line and "] " in line:
                            try: cnt = line.split("[")[1].split("]")[0]
                            except Exception: pass
                        if "下次" in line and "s (" in line:
                            try:
                                sec = int(line.split("下次 ")[1].split("s")[0])
                                interval = f"{sec}s"
                            except Exception: pass
                        if line[:2] in ("20","19") or "-" in line[:12]:
                            last = line[:19]
                except Exception:
                    pass
                return self._send(200, {"ok": True, "state": state,
                                        "count": cnt, "interval": interval, "last": last})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        if p == "/api/conf":
            try:
                data = json.loads(body)
                c = json.load(open(CONF)) if os.path.exists(CONF) else {}
                c["email"] = data.get("email", {})
                json.dump(c, open(CONF, "w"), ensure_ascii=False, indent=2)
                return self._send(200, {"ok": True})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        if p == "/api/test":
            try:
                hc = _load_hc()
                html = hc.build_alert_html("✅ 测试邮件", [
                    ("来源", "Moin 控制台"),
                    ("时间", time.strftime("%Y-%m-%d %H:%M:%S")),
                    ("说明", "收到此邮件表示邮件配置正确"),
                ], "ok")
                ok, err = hc.send_mail("Moin 控制台测试", html)
                return self._send(200, {"ok": ok, "error": err})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        if p == "/debug":
            try:
                item = {"action": "debug", "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                for _ in range(20):
                    if item["result"] is not None:
                        break
                    time.sleep(0.4)
                return self._send(200, item["result"] or {"ok": False, "error": "超时"})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        if p == "/read":
            try:
                item = {"action": "read", "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                for _ in range(20):
                    if item["result"] is not None:
                        break
                    time.sleep(0.4)
                return self._send(200, item["result"] or {"ok": False, "error": "超时"})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        if p == "/send":
            try:
                data = json.loads(body) if body else {}
                text = data.get("text", "").strip()
                sid = data.get("sid", "").strip()
                if not text:
                    return self._send(200, {"ok": False, "error": "消息为空"})
                # 预检：目标会话是否禁发（有 sid 时检查目标，无 sid 时检查当前页面）
                _bid = banned_ids()
                if sid and sid in _bid:
                    return self._send(200, {"ok": False,
                        "error": f"会话 {sid} 已标记为已死，禁止发送"})
                if not sid and not data.get("new") and is_banned(PG.get("page")):
                    return self._send(200, {"ok": False,
                        "error": "当前页面处于禁发会话，已阻止发送"})
                if data.get("new"):
                    item1 = {"action": "sendnew", "text": text, "result": None}
                    with SEND_LOCK:
                        SEND_QUEUE.append(item1)
                    for _ in range(180):
                        if item1["result"] is not None:
                            break
                        time.sleep(0.5)
                    r1 = item1["result"] or {"ok": False, "error": "超时"}
                    return self._send(200, r1)
                if sid:
                    NEWCHAT["active"] = False
                    item0 = {"action": "sendto", "tid": sid, "text": text, "result": None}
                    with SEND_LOCK:
                        SEND_QUEUE.append(item0)
                    for _ in range(180):
                        if item0["result"] is not None:
                            break
                        time.sleep(0.5)
                    return self._send(200, {"ok": bool(item0["result"]),
                                            "error": "" if item0["result"] else "发送失败"})
                if not (PG["page"] and STATE["logged"]):
                    return self._send(200, {"ok": False, "error": "未登录或浏览器未就绪"})
                item = {"text": text, "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                # 豆包生成上一条回复时输入框不可用，最长等 90 秒
                for _ in range(180):
                    if item["result"] is not None:
                        break
                    time.sleep(0.5)
                return self._send(200, {"ok": bool(item["result"]),
                                        "error": "" if item["result"] else "发送失败（豆包回复中或输入框不可用）"})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        if p == "/logout":
            try:
                if not PG.get("page"):
                    return self._send(200, {"ok": False, "error": "浏览器未就绪"})
                item = {"action": "logout", "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                for _ in range(60):
                    if item["result"] is not None:
                        break
                    time.sleep(0.5)
                ok = bool(item["result"])
                return self._send(200, {"ok": ok,
                                        "error": "" if ok else STATE["msg"]})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        if p == "/keepalive":
            try:
                body_data = json.loads(body) if body else {}
            except Exception:
                body_data = {}
            action = body_data.get("action", "")
            import subprocess
            if action == "start":
                r = subprocess.run(["systemctl","start","doubao-keepalive"],
                                   capture_output=True, text=True, timeout=15)
                return self._send(200, {"ok": r.returncode == 0, "error": r.stderr[:60]})
            if action == "stop":
                r = subprocess.run(["systemctl","stop","doubao-keepalive"],
                                   capture_output=True, text=True, timeout=15)
                return self._send(200, {"ok": r.returncode == 0, "error": r.stderr[:60]})
            if action == "settarget":
                sid = data.get("id", "")
                c2 = load_keepconf()
                c2["target"] = sid
                save_keepconf(c2)
                # 同步写入保活脚本读取的环境文件
                try:
                    open("/root/ka_target.txt", "w").write(sid)
                except Exception:
                    pass
                return self._send(200, {"ok": True, "target": sid})
            if action == "log":
                log = subprocess.run(["tail","-50","/root/keepalive_daemon.log"],
                                     capture_output=True, text=True, timeout=8).stdout
                return self._send(200, {"ok": True, "log": log[-3000:]})
            return self._send(200, {"ok": False, "error": "未知操作"})

        if p == "/notify":
            try:
                data = json.loads(body) if body else {}
                msg = f"{data.get('title','通知')}: {data.get('text','')}"
                logging.warning(msg)
                try:
                    with open("/root/notify.log", "a") as f:
                        f.write(f"{time.strftime('%F %T')} {msg}\n")
                except Exception:
                    pass
                return self._send(200, {"ok": True})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:60]})

        if p == "/restore":
            try:
                import subprocess
                out = []
                # 1. 拉起沙箱控制面 + 隧道（通过 unified 浏览器给豆包发指令）
                item = {"action": "restore", "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                for _ in range(150):
                    if item["result"] is not None:
                        break
                    time.sleep(1)
                out.append("沙箱恢复: " + json.dumps(item["result"], ensure_ascii=False)[:150])
                # 2. 启动保活
                r = subprocess.run(["systemctl","start","doubao-keepalive"],
                                   capture_output=True, text=True, timeout=15)
                out.append("保活启动: " + ("ok" if r.returncode == 0 else r.stderr[:60]))
                return self._send(200, {"ok": True, "out": "\n".join(out)})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        if p == "/sandboxping":
            try:
                import subprocess
                p1 = subprocess.run(["curl","-s","-m","6","http://127.0.0.1:17800/ping"],
                                    capture_output=True, text=True, timeout=10)
                if p1.returncode == 0 and p1.stdout.strip():
                    try:
                        d = json.loads(p1.stdout)
                        return self._send(200, {"ok": True, "up": d.get("uptime"),
                                                "host": d.get("host","")[:30]})
                    except Exception:
                        return self._send(200, {"ok": True, "up": None})
                return self._send(200, {"ok": False, "error": "沙箱隧道不通"})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        if p == "/mode":
            try:
                item = {"action": "mode", "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                for _ in range(40):
                    if item["result"] is not None:
                        break
                    time.sleep(0.5)
                return self._send(200, item["result"] or {"ok": False, "error": "超时"})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        if p == "/newchat":
            try:
                pg = PG.get("page")
                if not pg:
                    return self._send(200, {"ok": False, "error": "浏览器未就绪"})
                item = {"action": "newchat", "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                for _ in range(50):
                    if item["result"] is not None:
                        break
                    time.sleep(0.5)
                return self._send(200, item["result"] or {"ok": False, "error": "超时"})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        if p == "/getqr":
            try:
                pg = PG.get("page")
                if not pg:
                    return self._send(200, {"ok": False, "error": "浏览器未就绪"})
                item = {"action": "getqr", "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                for _ in range(50):
                    if item["result"] is not None:
                        break
                    time.sleep(0.5)
                return self._send(200, {"ok": bool(item["result"]),
                                        "error": "" if item["result"] else STATE["msg"]})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        if p == "/refresh":
            try:
                pg = PG.get("page")
                if not pg:
                    return self._send(200, {"ok": False, "error": "浏览器未就绪"})
                # 通过队列让浏览器线程执行（避免跨线程调用 Playwright）
                item = {"action": "refresh", "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                for _ in range(40):
                    if item["result"] is not None:
                        break
                    time.sleep(0.5)
                ok = bool(item["result"])
                return self._send(200, {"ok": ok,
                                        "error": "" if ok else STATE["msg"]})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        return self._send(404, {"error": "not found"})

    def do_POST(self):
        p = urlparse(self.path).path
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n).decode("utf-8", "ignore") if n else ""

        # ===== 保活启停 =====
        if p == "/keepalive":
            try:
                data = json.loads(body) if body else {}
            except Exception:
                data = {}
            action = data.get("action", "")
            import subprocess
            if action == "start":
                r = subprocess.run(["systemctl","start","doubao-keepalive"],
                                   capture_output=True, text=True, timeout=15)
                return self._send(200, {"ok": r.returncode == 0, "error": r.stderr[:60]})
            if action == "stop":
                r = subprocess.run(["systemctl","stop","doubao-keepalive"],
                                   capture_output=True, text=True, timeout=15)
                return self._send(200, {"ok": r.returncode == 0, "error": r.stderr[:60]})
            if action == "log":
                log = subprocess.run(["tail","-50","/root/keepalive_daemon.log"],
                                     capture_output=True, text=True, timeout=8).stdout
                return self._send(200, {"ok": True, "log": log[-4000:]})
            return self._send(200, {"ok": False, "error": "未知操作"})

        # ===== 会话管理 =====
        if p == "/sessions":
            try:
                data = json.loads(body) if body else {}
            except Exception:
                data = {}
            act = data.get("op", "")
            c = load_keepconf()
            if act == "refresh":
                item = {"action": "listsessions", "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                for _ in range(120):
                    if item["result"] is not None:
                        break
                    time.sleep(0.75)
                if not (item["result"] or {}).get("ok"):
                    return self._send(200, {"ok": False,
                        "error": (item["result"] or {}).get("error", "读取失败")})
                cur = {it["id"]: it["name"] for it in item["result"]["sessions"]}
                merged = {}
                for sid, name in cur.items():
                    old = c["sessions"].get(sid, {})
                    merged[sid] = {"name": name, "alive": old.get("alive", None),
                                   "keep": old.get("keep", False)}
                for sid in list(c["sessions"]):
                    if sid not in merged and str(sid).isdigit():
                        merged[sid] = {**c["sessions"][sid], "alive": False}
                c["sessions"] = merged
                if c.get("target") and c["target"] not in merged:
                    c["target"] = ""
                save_keepconf(c)
                return self._send(200, {"ok": True, **c})
            if act == "status":
                sid = data.get("id", "")
                if sid in c["sessions"]:
                    c["sessions"][sid]["alive"] = data.get("alive")
                    save_keepconf(c)
                return self._send(200, {"ok": True, **c})
            if act == "toggle":
                sid = data.get("id", "")
                if not sid:
                    for k in c["sessions"]:
                        c["sessions"][k]["keep"] = False
                    c["target"] = ""
                    save_keepconf(c)
                    return self._send(200, {"ok": True, **c})
                if sid not in c["sessions"]:
                    return self._send(200, {"ok": False, "error": "会话不存在"})
                for k in c["sessions"]:
                    c["sessions"][k]["keep"] = (k == sid)
                c["target"] = sid
                save_keepconf(c)
                try:
                    open("/root/ka_target.txt","w").write(sid)
                except Exception:
                    pass
                return self._send(200, {"ok": True, **c})
            return self._send(200, {"ok": False, "error": "未知操作"})

        # ===== 发消息 =====
        if p == "/send":
            try:
                data = json.loads(body) if body else {}
                text = (data.get("text") or "").strip()
                sid = (data.get("sid") or "").strip()
                if not text:
                    return self._send(200, {"ok": False, "error": "消息为空"})
                if not (PG.get("page") and STATE.get("logged")):
                    return self._send(200, {"ok": False, "error": "未登录或浏览器未就绪"})
                if data.get("new"):
                    item1 = {"action": "sendnew", "text": text, "result": None}
                    with SEND_LOCK:
                        SEND_QUEUE.append(item1)
                    for _ in range(180):
                        if item1["result"] is not None:
                            break
                        time.sleep(0.5)
                    return self._send(200, item1["result"] or {"ok": False, "error": "超时"})
                if sid:
                    NEWCHAT["active"] = False
                    item0 = {"action": "sendto", "tid": sid, "text": text, "result": None}
                    with SEND_LOCK:
                        SEND_QUEUE.append(item0)
                    for _ in range(180):
                        if item0["result"] is not None:
                            break
                        time.sleep(0.5)
                    return self._send(200, item0["result"] or {"ok": False, "error": "超时"})
                item = {"text": text, "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                for _ in range(180):
                    if item["result"] is not None:
                        break
                    time.sleep(0.5)
                return self._send(200, {"ok": bool(item["result"]),
                                        "error": "" if item["result"] else "发送失败"})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        # ===== 读页面 =====
        if p == "/read":
            try:
                item = {"action": "read", "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                for _ in range(20):
                    if item["result"] is not None:
                        break
                    time.sleep(0.4)
                return self._send(200, item["result"] or {"ok": False, "error": "超时"})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        # ===== debug =====
        if p == "/debug":
            try:
                item = {"action": "debug", "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                for _ in range(20):
                    if item["result"] is not None:
                        break
                    time.sleep(0.4)
                return self._send(200, item["result"] or {"ok": False, "error": "超时"})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        # ===== 云电脑模式 =====
        if p == "/mode":
            try:
                item = {"action": "mode", "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                for _ in range(60):
                    if item["result"] is not None:
                        break
                    time.sleep(0.5)
                return self._send(200, item["result"] or {"ok": False, "error": "超时"})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        # ===== 新建会话 =====
        if p == "/newchat":
            try:
                item = {"action": "newchat", "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                for _ in range(60):
                    if item["result"] is not None:
                        break
                    time.sleep(0.5)
                return self._send(200, item["result"] or {"ok": False, "error": "超时"})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        # ===== 扫码 =====
        if p == "/getqr":
            try:
                item = {"action": "getqr", "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                for _ in range(60):
                    if item["result"] is not None:
                        break
                    time.sleep(0.5)
                return self._send(200, item["result"] or {"ok": False, "error": "超时"})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        if p == "/logout":
            try:
                item = {"action": "logout", "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                for _ in range(60):
                    if item["result"] is not None:
                        break
                    time.sleep(0.5)
                ok = bool(item["result"])
                return self._send(200, {"ok": ok, "error": "" if ok else STATE["msg"]})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        # ===== 沙箱探测 =====
        if p == "/sandboxping":
            try:
                import subprocess
                r1 = subprocess.run(["curl","-s","-m","6","http://127.0.0.1:17800/ping"],
                                    capture_output=True, text=True, timeout=10)
                if r1.returncode == 0 and r1.stdout.strip():
                    try:
                        d = json.loads(r1.stdout)
                        return self._send(200, {"ok": True, "up": d.get("uptime"),
                                                "host": (d.get("host") or "")[:30]})
                    except Exception:
                        return self._send(200, {"ok": True, "up": None})
                return self._send(200, {"ok": False, "error": "沙箱隧道不通"})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        # ===== 邮件配置 =====
        if p == "/api/conf":
            try:
                data = json.loads(body)
                c = json.load(open(CONF)) if os.path.exists(CONF) else {}
                c["email"] = data.get("email", {})
                json.dump(c, open(CONF, "w"), ensure_ascii=False, indent=2)
                return self._send(200, {"ok": True})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        if p == "/api/test":
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location("hc", "/root/healthcheck.py")
                hc = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(hc)
                html = hc.build_alert_html("测试邮件", [
                    ("来源", "Moin 控制台"),
                    ("时间", time.strftime("%Y-%m-%d %H:%M:%S")),
                ], "ok")
                ok, err = hc.send_mail("Moin 测试", html)
                return self._send(200, {"ok": ok, "error": err})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        # ===== 一键恢复 =====
        if p == "/notify":
            try:
                data = json.loads(body) if body else {}
                msg = f"{data.get('title','通知')}: {data.get('text','')}"
                logging.warning(msg)
                try:
                    with open("/root/notify.log", "a") as f:
                        f.write(f"{time.strftime('%F %T')} {msg}\n")
                except Exception:
                    pass
                return self._send(200, {"ok": True})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:60]})

        if p == "/restore":
            try:
                import subprocess
                item = {"action": "restore", "result": None}
                with SEND_LOCK:
                    SEND_QUEUE.append(item)
                for _ in range(150):
                    if item["result"] is not None:
                        break
                    time.sleep(1)
                r = subprocess.run(["systemctl","start","doubao-keepalive"],
                                   capture_output=True, text=True, timeout=15)
                return self._send(200, {"ok": True,
                    "out": json.dumps(item["result"], ensure_ascii=False)[:200]})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)[:80]})

        return self._send(404, {"error": "not found"})


def main():
    threading.Thread(target=browser_worker, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    print(f"[unified] http://0.0.0.0:{PORT}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
