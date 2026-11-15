#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""accounts_db.py v3 — 账号/会话状态/全部开关配置持久化（SQLite）"""
import sqlite3, json, time

DB = "/root/doubao_accounts.db"

def conn():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    c.executescript("""
    CREATE TABLE IF NOT EXISTS accounts (
        uid TEXT PRIMARY KEY, name TEXT, phone TEXT, cookie_file TEXT, device_json TEXT,
        keep_conv_id TEXT DEFAULT '', keep_conv_name TEXT DEFAULT '',
        last_login_at INTEGER, created_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS login_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT, name TEXT, phone TEXT,
        at INTEGER, method TEXT, result TEXT
    );
    CREATE TABLE IF NOT EXISTS conv_status (
        uid TEXT, conv_id TEXT, name TEXT,
        alive INTEGER DEFAULT 1,           -- 1存活 0死亡
        dead_reason TEXT DEFAULT '',
        dead_at INTEGER,
        checked_at INTEGER,
        PRIMARY KEY(uid, conv_id)
    );
    CREATE TABLE IF NOT EXISTS settings (
        uid TEXT, key TEXT, value TEXT,
        PRIMARY KEY(uid, key)
    );
    """)
    c.commit(); return c

# ---- 账号 ----
def get_account(uid):
    c=conn(); r=c.execute("SELECT * FROM accounts WHERE uid=?",(uid,)).fetchone(); c.close()
    return dict(r) if r else None

def list_accounts():
    c=conn(); rows=[dict(r) for r in c.execute("SELECT * FROM accounts ORDER BY last_login_at DESC")]; c.close(); return rows

def upsert_account(uid,name,phone,cookie_file,device_json,at=None):
    at=at or int(time.time()); c=conn()
    old=c.execute("SELECT keep_conv_id,keep_conv_name FROM accounts WHERE uid=?",(uid,)).fetchone()
    k1=old["keep_conv_id"] if old else ""; k2=old["keep_conv_name"] if old else ""
    c.execute("""INSERT INTO accounts VALUES (?,?,?,?,?,?,?,?,?)
      ON CONFLICT(uid) DO UPDATE SET name=excluded.name,phone=excluded.phone,
      cookie_file=excluded.cookie_file,device_json=excluded.device_json,
      last_login_at=excluded.last_login_at,keep_conv_id=excluded.keep_conv_id,keep_conv_name=excluded.keep_conv_name""",
      (uid,name,phone,cookie_file,device_json,k1,k2,at,at))
    c.execute("INSERT INTO login_history (uid,name,phone,at,method,result) VALUES (?,?,?,?,?,?)",
              (uid,name,phone,at,"sms_api","ok"))
    c.commit(); c.close(); return get_account(uid)

def set_keep_conv(uid,conv_id,conv_name=""):
    c=conn(); c.execute("UPDATE accounts SET keep_conv_id=?,keep_conv_name=? WHERE uid=?",(conv_id,conv_name,uid)); c.commit(); c.close()

def history(limit=30):
    c=conn(); rows=[dict(r) for r in c.execute("SELECT * FROM login_history ORDER BY at DESC LIMIT ?",(limit,))]; c.close(); return rows

# ---- 会话状态 ----
def get_conv(uid,conv_id):
    c=conn(); r=c.execute("SELECT * FROM conv_status WHERE uid=? AND conv_id=?",(uid,conv_id)).fetchone(); c.close()
    return dict(r) if r else {"uid":uid,"conv_id":conv_id,"name":"","alive":1,"dead_reason":"","dead_at":0,"checked_at":0}

def list_conv(uid):
    c=conn(); rows=[dict(r) for r in c.execute("SELECT * FROM conv_status WHERE uid=?",(uid,))]; c.close(); return rows

def upsert_conv(uid,conv_id,name=None,alive=None,reason=None):
    cur=get_conv(uid,conv_id); c=conn()
    c.execute("""INSERT INTO conv_status (uid,conv_id,name,alive,dead_reason,dead_at,checked_at)
      VALUES (?,?,?,?,?,?,?)
      ON CONFLICT(uid,conv_id) DO UPDATE SET
        name=COALESCE(excluded.name,conv_status.name),
        alive=COALESCE(excluded.alive,conv_status.alive),
        dead_reason=COALESCE(excluded.dead_reason,conv_status.dead_reason),
        dead_at=COALESCE(excluded.dead_at,conv_status.dead_at),
        checked_at=excluded.checked_at""",
      (uid,conv_id,
       name if name is not None else cur["name"],
       alive if alive is not None else cur["alive"],
       reason if reason is not None else cur["dead_reason"],
       int(time.time()) if alive==0 else cur["dead_at"],
       int(time.time())))
    c.commit(); c.close()

def mark_dead(uid,conv_id,reason):
    upsert_conv(uid,conv_id,alive=0,reason=reason)

def mark_alive(uid,conv_id):
    upsert_conv(uid,conv_id,alive=1,reason="")

# ---- 设置（所有开关持久化）----
DEFAULT_SETTINGS = {
    "auto_new_on_dead": "0",        # 死亡自动新开会话，默认关
    "rename_prefix": "老王",         # 新会话命名前缀
    "rename_counter": "0",          # 计数器（A/B/C 或 1/2/3）
    "rename_style": "letter",       # letter(A,B,C) / number(1,2,3)
    "keep_interval_sec": "1800",    # 保活任务间隔
    "wake_interval_sec": "1200",    # 恢复指令间隔
    "cloud_mode": "9",              # 云电脑模式
    "death_keywords": "不能执行|无法执行|拒绝执行|高风险|高危操作|标记为高风险|不执行|违规|安全限制",
}
def get_setting(uid,key,default=None):
    c=conn(); r=c.execute("SELECT value FROM settings WHERE uid=? AND key=?",(uid,key)).fetchone(); c.close()
    return r["value"] if r else (DEFAULT_SETTINGS.get(key,default))

def set_setting(uid,key,value):
    c=conn(); c.execute("INSERT INTO settings VALUES (?,?,?) ON CONFLICT(uid,key) DO UPDATE SET value=excluded.value",(uid,key,str(value))); c.commit(); c.close()

def all_settings(uid):
    c=conn(); rows={r["key"]:r["value"] for r in c.execute("SELECT * FROM settings WHERE uid=?",(uid,))}; c.close()
    out=dict(DEFAULT_SETTINGS); out.update(rows); return out

def next_conv_name(uid):
    s=all_settings(uid); prefix=s["rename_prefix"]; n=int(s["rename_counter"] or 0)+1
    style=s["rename_style"]
    if style=="number": suffix=str(n)
    else:
        # 0->A 1->B ... 25->Z 26->AA
        x=n-1; suffix=""
        while True:
            suffix=chr(65+x%26)+suffix; x=x//26-1
            if x<0: break
    set_setting(uid,"rename_counter",str(n))
    return prefix+"（"+suffix+"）"
