#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""keep_test_worker.py — 保活功能测试：3s/7s/10s 三次发送"""
import sys, time, json
sys.path.insert(0,"/root")
import accounts_db as DB, conv_api as API
F="/root/keep_test_result.json"
try: uid=json.load(open("/root/active_account.json")).get("uid","")
except Exception: uid=""
acc=DB.get_account(uid) if uid else None
cid=acc["keep_conv_id"] if acc else ""
if not cid:
    json.dump({"ok":False,"err":"no keep conv","results":[]},open(F,"w")); sys.exit(0)
plan=[(3,"你好"),(4,"你好你好"),(3,"你好呀")]  # 累计 3/7/10 秒
results=[]; t0=time.time()
for delay,text in plan:
    time.sleep(delay)
    sse=API.send_full(cid,text)
    hit=API.death_check(sse, DB.all_settings(uid)["death_keywords"])
    if hit: DB.mark_dead(uid,cid,"保活测试命中: "+hit)
    results.append({"at":round(time.time()-t0),"text":text,"ok":bool(sse),"death":hit,"reply":API.extract_reply(sse)[:100]})
    json.dump({"ok":True,"running":len(results)<3,"cid":cid,"results":results},open(F,"w"),ensure_ascii=False)
json.dump({"ok":True,"running":False,"cid":cid,"results":results},open(F,"w"),ensure_ascii=False)
