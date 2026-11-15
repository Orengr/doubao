#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""login_api.py — 纯接口短信登录（无扫码、无 UI 交互）
依赖：Xvfb :99 + 非 headless chromium CDP 9222（bdms 签名环境）
用法：
  python3 login_api.py send <phone>      -> 发验证码
  python3 login_api.py verify <phone> <code> -> 提交登录，返回账号 JSON
"""
import json, sys, time, urllib.request, websocket, subprocess

CDP = "http://127.0.0.1:9222"
FP = "verify_mwea228o_WY5ckeMo_3xNI_4v83_AnQH_LKQ7pl55QA3v"
Q = ("passport_jssdk_version=4.4.6&passport_jssdk_type=normal&is_from_ttaccountsdk=1"
     "&aid=497858&language=zh&account_app_language=en-US&p_ca=4.0.26"
     "&fp=" + FP + "&verifyFp=" + FP + "&multi_login=1&account_sdk_source=web")

def page_ws():
    tabs = json.loads(urllib.request.urlopen(CDP + "/json/list", timeout=10).read())
    page = next((t for t in tabs if t["type"] == "page"), None)
    if not page: raise RuntimeError("no CDP page")
    return page["webSocketDebuggerUrl"]

def eval_js(js, timeout=60):
    ws = websocket.create_connection(page_ws(), timeout=timeout)
    ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                        "params": {"expression": js, "awaitPromise": True, "returnByValue": True}}))
    end = time.time() + timeout
    out = None
    while time.time() < end:
        try:
            r = json.loads(ws.recv())
            if r.get("id") == 1:
                out = r.get("result", {}).get("result", {}).get("value")
                break
        except Exception: break
    ws.close()
    return out

def x05(s):
    return "".join(f"{b^5:02x}" for b in s.encode())

def browser_fetch(url, body):
    """在页面上下文发 POST（同源 cookie + bdms 签名环境）；返回响应文本"""
    js = """
(async () => {
  const r = await fetch(%s, {
    method:'POST', credentials:'include',
    headers:{'Content-Type':'application/x-www-form-urlencoded'},
    body: %s
  });
  return await r.text();
})()
""" % (json.dumps(url), json.dumps(body))
    return eval_js(js, 40) or ""

def signed_url(path, base_q):
    """bdms.frontierSign 生成 X-Bogus 附加到 URL"""
    js = """
(() => {
  const s = window.bdms.frontierSign({url: %s});
  return s['X-Bogus'] || '';
})()
""" % json.dumps(path + "?" + base_q)
    return eval_js(js, 20) or ""

def send_code(phone):
    q = Q + "&ts=" + str(int(time.time()))
    xb = signed_url("/passport/web/send_code/", q)
    url = "https://accounts.doubao.com/passport/web/send_code/?" + q + "&X-Bogus=" + xb
    body = "mix_mode=1&mobile=" + x05("+86 " + phone) + "&type=3731&is6Digits=1&fixed_mix_mode=1"
    return browser_fetch(url, body)

def sms_login(phone, code):
    q = Q + "&ts=" + str(int(time.time()))
    xb = signed_url("/passport/web/sms_login/", q)
    url = "https://accounts.doubao.com/passport/web/sms_login/?" + q + "&X-Bogus=" + xb
    body = "mix_mode=1&mobile=" + x05("+86 " + phone) + "&code=" + x05(code) + "&login_only=false&fixed_mix_mode=1"
    return browser_fetch(url, body)

def export_cookies():
    """导出全量 cookie（含 httpOnly）+ 设备身份，存档案"""
    bws = json.loads(urllib.request.urlopen(CDP + "/json/version").read())["webSocketDebuggerUrl"]
    ws = websocket.create_connection(bws, timeout=20)
    ws.send(json.dumps({"id": 1, "method": "Storage.getCookies"}))
    end = time.time() + 15
    cookies = []
    while time.time() < end:
        r = json.loads(ws.recv())
        if r.get("id") == 1:
            cookies = r["result"]["cookies"]
            break
    ws.close()
    pairs = [c["name"] + "=" + c["value"] for c in cookies if "doubao" in c["domain"]]
    ident = json.loads(eval_js("""
(() => {
  const ck=Object.fromEntries(document.cookie.split('; ').map(s=>{const i=s.indexOf('=');return[s.slice(0,i),s.slice(i+1)];}));
  const tea=JSON.parse(localStorage.getItem('__tea_cache_tokens_497858')||'{}');
  const sam=JSON.parse(localStorage.getItem('samantha_web_web_id')||'{}');
  return JSON.stringify({ua:navigator.userAgent, device_id:sam.web_id||'', web_id:tea.web_id||'',
    fp:ck['s_v_web_id']||'', msToken:ck['msToken']||'', uid:localStorage.getItem('flow_tea_user_id')||''});
})()
""") or "{}")
    return pairs, ident

def main():
    cmd = sys.argv[1]
    phone = sys.argv[2]
    if cmd == "send":
        print(send_code(phone))
    elif cmd == "verify":
        code = sys.argv[3]
        resp = sms_login(phone, code)
        try:
            d = json.loads(resp)
        except Exception:
            print(json.dumps({"ok": False, "raw": resp[:300]})); return
        data = d.get("data", {})
        uid = str(data.get("user_id_str") or data.get("user_id") or "")
        if not uid or "error_code" in data:
            print(json.dumps({"ok": False, "resp": d}, ensure_ascii=False)[:400]); return
        name = data.get("screen_name") or data.get("name") or ""
        pairs, ident = export_cookies()
        ck_file = "/root/ck_%s.txt" % uid
        open(ck_file, "w").write("\n".join(pairs))
        open("/root/ck_live2.txt", "w").write("\n".join(pairs))
        # 同步给当前 active 账号
        out = {"ok": True, "uid": uid, "name": name, "phone": phone,
               "cookie_file": ck_file, "device": ident, "cookies": len(pairs)}
        print(json.dumps(out, ensure_ascii=False))
    else:
        print("unknown cmd")

if __name__ == "__main__":
    main()
