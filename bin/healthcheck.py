#!/usr/bin/env python3
"""
healthcheck.py — cookie 健康检查 + 邮件告警

功能：
1. 检查关键 cookie 是否存在
2. 记录 cookie 指纹，检测是否自动续期
3. 发现异常发邮件通知
"""
import os, json, time, hashlib, logging, smtplib, ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

CONF = os.environ.get("HEALTHCONF", "/root/healthconf.json")
STATE = os.environ.get("HEALTH_STATE", "/root/health_state.json")
LOG = os.environ.get("HEALTH_LOG", "/root/healthcheck.log")

# 延迟初始化 logging：模块被 import 时（如测试环境）不写文件
log = logging.getLogger("hc")
log.setLevel(logging.INFO)
if not log.handlers:
    try:
        _fh = logging.FileHandler(LOG, encoding="utf-8")
        _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        log.addHandler(_fh)
        log.addHandler(logging.StreamHandler())
    except (PermissionError, OSError):
        # 无权限写日志（如 CI/测试环境）→ 只输出到 stdout
        logging.basicConfig(level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s")
        log = logging.getLogger("hc")

# 关键 cookie（兼容新旧两套体系）
# 新体系：sessionid_ss / sid_guard / uid_tt_ss / sid_ucp_v1
# 旧体系：sessionid / sid_tt / uid_tt
KEY_GROUPS = {
    "session":  ["sessionid_ss", "sessionid"],       # 至少有一个
    "guard":    ["sid_guard", "sid_ss"],             # 至少有一个
    "uid":      ["uid_tt_ss", "uid_tt"],             # 至少有一个
}
# bd_sso_hi3jfd 为可选长期 token：新登录体系可能不下发，缺失不算异常
# 兼容旧代码
KEY_COOKIES = ["sessionid_ss", "sid_guard", "bd_sso_hi3jfd", "uid_tt_ss"]


def load_conf():
    """读取配置（邮箱等）"""
    if os.path.exists(CONF):
        try:
            return json.load(open(CONF))
        except Exception:
            pass
    return {}


def load_state():
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE))
        except Exception:
            pass
    return {"last_fp": "", "last_check": 0, "alerts_sent": 0, "history": []}


def save_state(s):
    try:
        json.dump(s, open(STATE, "w"), ensure_ascii=False, indent=2)
    except Exception:
        pass


def fingerprint(cookies):
    """生成 cookie 指纹（用于检测续期变化）"""
    parts = []
    for group, names in KEY_GROUPS.items():
        for n in names:
            v = cookies.get(n, "")
            if v:
                parts.append(f"{n}={v[:16]}")
                break
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def check_cookie(cookie_file="/root/ck_full.txt"):
    """检查 cookie 文件健康度"""
    if not os.path.exists(cookie_file):
        return {"ok": False, "reason": "cookie 文件不存在", "cookies": {}}

    cookies = {}
    for line in open(cookie_file):
        line = line.strip()
        if "=" in line:
            k, v = line.split("=", 1)
            cookies[k.strip()] = v.strip()

    # 按组检测：每组至少有一个
    present = {}
    missing = []
    for group, names in KEY_GROUPS.items():
        found = [n for n in names if n in cookies and cookies[n]]
        present[group] = found[0] if found else None
        if not found:
            missing.append(group + "(" + "/".join(names) + ")")

    return {
        "ok": len(missing) == 0,
        "missing": missing,
        "present": present,
        "count": len(cookies),
        "fp": fingerprint(cookies),
        "cookies": cookies,
    }


def send_mail(subject, html):
    """发邮件"""
    c = load_conf().get("email", {})
    if not c.get("enabled"):
        log.info("邮件未启用，跳过")
        return False, "未配置"

    host = c.get("smtp_host", "")
    port = int(c.get("smtp_port", 465))
    user = c.get("smtp_user", "")
    pwd = c.get("smtp_pass", "")
    to = c.get("to", "")

    if not all([host, user, pwd, to]):
        log.warning("邮件配置不完整")
        return False, "配置不完整"

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = to
        msg.attach(MIMEText(html, "html", "utf-8"))

        if port == 465:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=20) as s:
                s.login(user, pwd)
                s.sendmail(user, [to], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.starttls()
                s.login(user, pwd)
                s.sendmail(user, [to], msg.as_string())

        log.info(f"邮件已发送: {subject}")
        return True, "ok"
    except Exception as e:
        log.error(f"邮件发送失败: {str(e)[:100]}")
        return False, str(e)[:100]


def build_alert_html(title, items, level="warn"):
    color = {"ok": "#3ddc97", "warn": "#ffb648", "err": "#ff5c7c"}.get(level, "#ffb648")
    rows = "".join(
        f'<tr><td style="padding:8px 12px;border-bottom:1px solid #eee;color:#666">{k}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #eee;font-weight:600">{v}</td></tr>'
        for k, v in items)
    return f"""<!DOCTYPE html><html><body style="font-family:-apple-system,sans-serif;
margin:0;padding:20px;background:#f5f6f8">
<div style="max-width:560px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;
box-shadow:0 2px 12px rgba(0,0,0,.06)">
<div style="background:{color};padding:18px 22px">
<h2 style="margin:0;color:#fff;font-size:17px;font-weight:600">{title}</h2></div>
<table style="width:100%;border-collapse:collapse;font-size:14px">{rows}</table>
<div style="padding:14px 22px;background:#fafbfc;color:#999;font-size:12px;
border-top:1px solid #eee">Moin Server 自动监控 · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
</div></body></html>"""


def server_alive():
    """
    真实校验：向 unified 请求当前页面状态，
    判断是否仍处于登录态（页面在会话内 = 已登录）
    返回 True/False/None(无法判断)
    """
    try:
        import urllib.request as _u
        req = _u.Request("http://127.0.0.1:18800/debug", data=b"", method="POST")
        d = json.loads(_u.urlopen(req, timeout=40).read())
        info = d.get("info", {})
        url = info.get("url", "") or ""
        title = info.get("page_title", "") or ""
        if "from_logout" in url:
            return False
        if "登录" in title or title.strip() == "豆包" and "/chat" not in url:
            return None
        if "/chat/" in url and "豆包" in title:
            return True
        return None
    except Exception:
        return None


def run():
    st = load_state()
    ck = check_cookie()

    # 服务端真实校验
    sv = server_alive()
    if sv is False:
        log.error("服务端已拒绝会话（页面被踢回登录）")
        if time.time() - st.get("last_alert", 0) > 21600:
            send_mail("⚠️ 豆包登录已失效（服务端拒绝）",
                      build_alert_html("豆包登录失效", [
                          ("原因", "服务端吊销 session，需重新扫码"),
                          ("操作", "打开 18800 → 扫码登录 → 获取二维码"),
                          ("Cookie 数", ck.get("count", 0)),
                      ], "err"))
            st["last_alert"] = time.time()
            st["alerts_sent"] = st.get("alerts_sent", 0) + 1
            save_state(st)
        return
    if sv is True:
        st["server_ok"] = True
        st["server_ok_at"] = time.time()
    else:
        st["server_ok"] = None
    save_state(st)

    # 1. 检查 cookie 存在性
    if not ck["ok"]:
        log.error(f"cookie 不完整，缺失: {ck.get('missing')}")
        # 同一问题 6 小时内不重复告警
        if time.time() - st.get("last_alert", 0) > 21600:
            send_mail(
                "⚠️ 豆包登录失效",
                build_alert_html("豆包登录失效", [
                    ("问题", "cookie 缺失"),
                    ("缺失项", ", ".join(ck.get("missing", []))),
                    ("当前数量", ck.get("count", 0)),
                    ("处理", "请访问登录页重新扫码"),
                ], "err"))
            st["last_alert"] = time.time()
            st["alerts_sent"] = st.get("alerts_sent", 0) + 1
        save_state(st)
        return

    # 2. 检查指纹是否变化（续期证据）
    fp = ck["fp"]
    prev = st.get("last_fp", "")
    if prev and fp != prev:
        log.info(f"cookie 已变化（自动续期生效）{prev} → {fp}")
        st["history"] = (st.get("history", []) + [{
            "time": datetime.now().isoformat(),
            "fp": fp, "type": "renewed"
        }])[-30:]

    if not prev:
        log.info(f"首次检查，指纹 {fp}")

    st["last_fp"] = fp
    st["last_check"] = time.time()
    st["cookie_count"] = ck["count"]
    save_state(st)

    log.info(f"健康检查通过: cookie={ck['count']} 指纹={fp}")


if __name__ == "__main__":
    run()
