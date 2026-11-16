#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""boot_restore.py — 开机恢复：注入 active 账号 cookie + 云电脑模式 + 导航"""
import json, os, time, urllib.request, websocket, subprocess, sys
CDP="http://127.0.0.1:9222"
def wait_cdp(n=30):
    for _ in range(n):
        try:
            urllib.request.urlopen(CDP+"/json/version",timeout=3); return True
        except Exception: time.sleep(1)
    return False
def page():
    tabs=json.loads(urllib.request.urlopen(CDP+"/json/list",timeout=10).read())
    return next((t for t in tabs if t["type"]=="page"),None)
def main():
    if not wait_cdp(): print("CDP_UNAVAILABLE"); return
    # active 账号
    try: a=json.load(open("/root/active_account.json"))
    except Exception: a={}
    f=a.get("cookie_file") or "/root/ck_live2.txt"
    if not os.path.exists(f): print("NO_COOKIE_FILE",f); return
    raw = open(f, encoding="utf-8").read().strip()
    # 支持两种格式：分号分隔的单行，或每行一个
    if ";" in raw:
        parts = [x.strip() for x in raw.split(";") if "=" in x]
    else:
        parts = [x.strip() for x in raw.splitlines() if "=" in x]
    cookies = []
    for l in parts:
        n, v = l.split("=", 1)
        n = n.strip(); v = v.strip()
        if n and v:
            cookies.append({"name": n, "value": v, "domain": ".doubao.com",
                            "path": "/", "secure": True, "httpOnly": False, "sameSite": "None"})
    bws=json.loads(urllib.request.urlopen(CDP+"/json/version").read())["webSocketDebuggerUrl"]
    w=websocket.create_connection(bws,timeout=20)
    w.send(json.dumps({"id":1,"method":"Storage.setCookies","params":{"cookies":cookies}}))
    while True:
        if json.loads(w.recv()).get("id")==1: break
    w.close()
    # 导航到会话页
    t=page()
    if t:
        w=websocket.create_connection(t["webSocketDebuggerUrl"],timeout=30)
        w.send(json.dumps({"id":2,"method":"Page.navigate","params":{"url":"https://www.doubao.com/chat/"}}))
        time.sleep(1); w.close()
    time.sleep(6)
    # 恢复模式（导航后 localStorage 可能重置，addScriptToEvaluateOnNewDocument 持久化）
    t=page()
    if t:
        w=websocket.create_connection(t["webSocketDebuggerUrl"],timeout=30)
        w.send(json.dumps({"id":3,"method":"Page.addScriptToEvaluateOnNewDocument","params":{"source":"localStorage.setItem('mode_select_value','9');"}}))
        w.send(json.dumps({"id":4,"method":"Runtime.evaluate","params":{"expression":"localStorage.setItem('mode_select_value','9'); localStorage.getItem('mode_select_value')","returnByValue":True}}))
        end=time.time()+15
        while time.time()<end:
            try:
                r=json.loads(w.recv())
                if r.get("id")==4: break
            except Exception: break
        w.close()
    print(json.dumps({"ok":True,"cookies":len(cookies),"mode":"9","account":a.get("uid","")}))
if __name__=="__main__": main()
