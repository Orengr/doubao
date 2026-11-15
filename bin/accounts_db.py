#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""accounts_db.py — 账号/设备/登录历史/保活会话持久化（SQLite）"""
import sqlite3, json, os, time

DB = "/root/doubao_accounts.db"

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS accounts (
        uid TEXT PRIMARY KEY,
        name TEXT, phone TEXT,
        cookie_file TEXT,
        device_json TEXT,
        keep_conv_id TEXT DEFAULT '',
        keep_conv_name TEXT DEFAULT '',
        last_login_at INTEGER,
        created_at INTEGER
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS login_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid TEXT, name TEXT, phone TEXT, at INTEGER,
        method TEXT, result TEXT
    )""")
    c.commit()
    return c

def get_account(uid):
    c = conn()
    r = c.execute("SELECT * FROM accounts WHERE uid=?", (uid,)).fetchone()
    c.close()
    return dict(r) if r else None

def list_accounts():
    c = conn()
    rows = [dict(r) for r in c.execute("SELECT * FROM accounts ORDER BY last_login_at DESC").fetchall()]
    c.close()
    return rows

def upsert_account(uid, name, phone, cookie_file, device_json, at=None):
    at = at or int(time.time())
    c = conn()
    old = c.execute("SELECT keep_conv_id, keep_conv_name FROM accounts WHERE uid=?", (uid,)).fetchone()
    keep_id = old["keep_conv_id"] if old else ""
    keep_name = old["keep_conv_name"] if old else ""
    c.execute("""INSERT INTO accounts (uid,name,phone,cookie_file,device_json,keep_conv_id,keep_conv_name,last_login_at,created_at)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(uid) DO UPDATE SET name=excluded.name, phone=excluded.phone,
          cookie_file=excluded.cookie_file, device_json=excluded.device_json,
          last_login_at=excluded.last_login_at, keep_conv_id=excluded.keep_conv_id,
          keep_conv_name=excluded.keep_conv_name""",
        (uid, name, phone, cookie_file, device_json, keep_id, keep_name, at, at))
    c.execute("INSERT INTO login_history (uid,name,phone,at,method,result) VALUES (?,?,?,?,?,?)",
              (uid, name, phone, at, "sms_api", "ok"))
    c.commit(); c.close()
    return get_account(uid)

def set_keep_conv(uid, conv_id, conv_name=""):
    c = conn()
    c.execute("UPDATE accounts SET keep_conv_id=?, keep_conv_name=? WHERE uid=?", (conv_id, conv_name, uid))
    c.commit(); c.close()

def history(limit=20):
    c = conn()
    rows = [dict(r) for r in c.execute("SELECT * FROM login_history ORDER BY at DESC LIMIT ?", (limit,)).fetchall()]
    c.close()
    return rows
