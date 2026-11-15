#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloudmode.py — 读取/设置页面模式（9=云电脑, 0=对话）
说明：模式切换不发独立接口，是账号级 localStorage mode_select_value，
发消息时 option.general_task_param(云电脑) 或 model_config(对话) 随之变化。
"""
import json, urllib.request, websocket, sys
CDP="http://127.0.0.1:9222"
def page():
    tabs=json.loads(urllib.request.urlopen(CDP+"/json/list",timeout=10).read())
    return next((t["webSocketDebuggerUrl"] for t in tabs if t["type"]=="page"),None)
def run(expr, timeout=20):
    w=websocket.create_connection(page(),timeout=timeout)
    w.send(json.dumps({"id":1,"method":"Runtime.evaluate","params":{"expression":expr,"returnByValue":True}}))
    end=__import__("time").time()+timeout
    out=None
    while __import__("time").time()<end:
        try:
            r=json.loads(w.recv())
            if r.get("id")==1: out=r.get("result",{}).get("result",{}).get("value"); break
        except Exception: break
    w.close(); return out
if __name__=="__main__":
    if len(sys.argv)>1:
        v=sys.argv[1]
        print(json.dumps({"ok":True,"set":v,"result":run("localStorage.setItem('mode_select_value','%s'); localStorage.getItem('mode_select_value')"%v)}))
    else:
        v=run("localStorage.getItem('mode_select_value')") or "0"
        labels={"9":"云电脑","0":"对话","1":"工作任务","2":"本地电脑"}
        print(json.dumps({"value":v,"label":labels.get(v,"模式"+v)}))
