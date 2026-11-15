#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""keepctl.py — 保活引擎控制（按账号档案的 keep_conv_id）"""
import json, subprocess, os, sys, time
sys.path.insert(0, "/root")
import accounts_db as DB

CONF = "/root/keepconf.json"
STATE = "/root/ka_state.json"

def status():
    try:
        a = json.load(open("/root/active_account.json"))
    except Exception:
        a = {}
    acc = DB.get_account(a.get("uid","")) if a.get("uid") else None
    active = subprocess.run(["systemctl","is-active","ka-pure"],capture_output=True,text=True).stdout.strip()
    return {"active_uid": a.get("uid",""), "account": acc, "service": active,
            "keep_conv_id": acc["keep_conv_id"] if acc else "",
            "keep_conv_name": acc["keep_conv_name"] if acc else ""}

def set_keep(uid, conv_id, conv_name=""):
    DB.set_keep_conv(uid, conv_id, conv_name)
    cfg = json.load(open(CONF)) if os.path.exists(CONF) else {"sessions": {}}
    cfg["target"] = conv_id
    for cid, s in cfg.get("sessions", {}).items():
        s["keep"] = (cid == conv_id)
        if cid == conv_id and conv_name: s["name"] = conv_name
    json.dump(cfg, open(CONF,"w"), ensure_ascii=False, indent=1)
    return {"ok": True, "conv_id": conv_id, "conv_name": conv_name}

def activate(uid, conv_id=None):
    acc = DB.get_account(uid)
    if not acc: return {"ok": False, "err": "account not found"}
    if conv_id: set_keep(uid, conv_id)
    else: conv_id = acc["keep_conv_id"]
    if not conv_id: return {"ok": False, "err": "no keep conv configured"}
    json.dump({"uid": uid, "name": acc["name"], "cookie_file": acc["cookie_file"]},
              open("/root/active_account.json","w"), ensure_ascii=False)
    # 确保当前浏览器/发送器用这个账号的 cookie
    subprocess.run(["python3","/root/inject_ck.py", acc["cookie_file"]], capture_output=True, text=True, timeout=40)
    subprocess.run(["systemctl","restart","ka-pure"], capture_output=True, text=True, timeout=30)
    # 立即触发一次可见保活（用户点"启用保活"马上能看到消息和状态）
    once = subprocess.run(["python3","/root/ka_once.py"], capture_output=True, text=True, timeout=130)
    return {"ok": True, "uid": uid, "conv_id": conv_id, "service": "restarted", "immediate": once.stdout.strip()[:300]}

if __name__ == "__main__":
    c = sys.argv[1]
    if c == "status": print(json.dumps(status(), ensure_ascii=False))
    elif c == "setkeep": print(json.dumps(set_keep(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv)>4 else ""), ensure_ascii=False))
    elif c == "activate": print(json.dumps(activate(sys.argv[2], sys.argv[3] if len(sys.argv)>3 else None), ensure_ascii=False))
