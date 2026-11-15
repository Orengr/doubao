#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inject_ck.py — 把账号 cookie 注入 CDP 浏览器，恢复登录态"""
import json, urllib.request, websocket, sys, time
CDP="http://127.0.0.1:9222"
f=sys.argv[1] if len(sys.argv)>1 else "/root/ck_live2.txt"
pairs=[l.strip() for l in open(f) if "=" in l]
cookies=[{"name":l.split("=",1)[0],"value":l.split("=",1)[1],"domain":".doubao.com","path":"/","secure":True,"httpOnly":False,"sameSite":"None"} for l in pairs]
bws=json.loads(urllib.request.urlopen(CDP+"/json/version").read())["webSocketDebuggerUrl"]
ws=websocket.create_connection(bws,timeout=20)
ws.send(json.dumps({"id":1,"method":"Storage.setCookies","params":{"cookies":cookies}}))
while True:
    r=json.loads(ws.recv())
    if r.get("id")==1: break
ws.close()
# 导航到会话页刷新登录态
tabs=json.loads(urllib.request.urlopen(CDP+"/json/list",timeout=10).read())
tab=next((t for t in tabs if t["type"]=="page"),None)
if tab:
    w=websocket.create_connection(tab["webSocketDebuggerUrl"],timeout=30)
    w.send(json.dumps({"id":2,"method":"Page.navigate","params":{"url":"https://www.doubao.com/chat/"}}))
    time.sleep(1)
    w.close()
print(json.dumps({"ok":True,"cookies":len(cookies)}))
