#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ka_once.py — 立即执行一次保活发送（启用按钮触发，用户马上能看到消息+状态）"""
import sys, json, time, logging
sys.path.insert(0,"/root")
import accounts_db as DB, conv_api as API
logging.basicConfig(level=logging.INFO,format="%(asctime)s %(message)s")
log=logging.getLogger("once")
uid=json.load(open("/root/active_account.json")).get("uid","")
acc=DB.get_account(uid) if uid else None
if not acc or not acc["keep_conv_id"]:
    log.error("无保活会话"); print(json.dumps({"ok":False,"err":"no keep conv"})); sys.exit(0)
cid=acc["keep_conv_id"]; cv=DB.get_conv(uid,cid)
if cv["alive"]==0:
    log.warning("会话已死亡，跳过发送"); print(json.dumps({"ok":False,"err":"conv dead"})); sys.exit(0)
s=DB.all_settings(uid)
text="保活自检 {ts}：请确认沙箱服务状态，简要回复即可".replace("{ts}",str(int(time.time())))
log.info("立即发送 → %s",cid)
sse=API.send_full(cid,text)
reply=API.extract_reply(sse)
hit=API.death_check(sse,s["death_keywords"])
if hit:
    DB.mark_dead(uid,cid,"启用保活自检命中: "+hit)
    log.warning("标记死亡: %s",hit)
else:
    DB.upsert_conv(uid,cid,alive=1)
print(json.dumps({"ok":True,"conv_id":cid,"reply":reply[:150],"death":hit},ensure_ascii=False))
