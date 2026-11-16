#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_agent_extra.py — agent 数据库/cron/备份/文件 逻辑测试"""
import os, re, json, tempfile, shutil, subprocess, sqlite3

PEND = tempfile.mkdtemp()
os.makedirs(os.path.join(PEND,"log"), exist_ok=True)
os.makedirs(os.path.join(PEND,"state"), exist_ok=True)

def sh(cmd, t=30, cwd=None):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=t, cwd=cwd)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return 1, str(e)

def safe(path):
    p = os.path.abspath(path)
    if not p.startswith(PEND) and not p.startswith("/home/user") and not p.startswith("/tmp"):
        return None
    return p

PASS=0; FAIL=0
def chk(n,c,e=""):
    global PASS,FAIL
    if c: PASS+=1; print("  PASS  "+n+" "+str(e))
    else: FAIL+=1; print("  FAIL  "+n+" "+str(e))

print("="*52)
print(" agent 数据库/cron/备份/文件 逻辑测试")
print("="*52)

# ---- 文件操作 ----
print("\n[1] 文件读写")
f = os.path.join(PEND, "test.txt")
open(f,"w",encoding="utf-8").write("hello\nworld\n")
chk("写入成功", os.path.exists(f))
chk("读取成功", open(f,encoding="utf-8").read()=="hello\nworld\n")
chk("safe()放行PEND内", safe(f)==os.path.abspath(f))
chk("safe()拒绝越界", safe("/etc/passwd") is None)

print("\n[2] 目录列表")
os.makedirs(os.path.join(PEND,"www","a"), exist_ok=True)
os.makedirs(os.path.join(PEND,"www","b"), exist_ok=True)
items = sorted(os.listdir(os.path.join(PEND,"www")))
chk("列出2个目录", items==["a","b"], items)

print("\n[3] 日志读取")
lg = os.path.join(PEND,"log","t.log")
open(lg,"w").write("\n".join("line%d"%i for i in range(100)))
lines = open(lg,errors="ignore").readlines()[-20:]
chk("读最后20行", len(lines)==20)
chk("最后一行是line99", lines[-1].strip()=="line99")

print("\n[4] cron 格式校验")
def cron_add(expr, cmd):
    # 只验证格式合法性，不真的写 crontab（避免污染环境）
    parts = expr.split()
    if len(parts) != 5: return {"ok": False, "error": "cron需5段"}
    for p in parts:
        if not re.match(r'^[\d*/,?-]+$', p): return {"ok": False, "error": "非法字符"}
    return {"ok": True, "line": expr+" "+cmd}

chk("标准cron通过", cron_add("*/5 * * * *","/bin/echo hi")["ok"])
chk("5段校验", cron_add("* * *","x")["ok"]==False)
chk("非法字符拒绝", cron_add("abc * * * *","x")["ok"]==False)
chk("复杂表达式通过", cron_add("0 9-18/2 * * 1-5","/bin/x")["ok"])

print("\n[5] 备份逻辑")
def backup():
    ts = "test"
    outdir = os.path.join(PEND,"backup"); os.makedirs(outdir, exist_ok=True)
    tarf = os.path.join(outdir,"data_"+ts+".tar.gz")
    os.makedirs(os.path.join(PEND,"www"), exist_ok=True)
    open(os.path.join(PEND,"www","x.html"),"w").write("<h1>x</h1>")
    dirs = [d for d in ("www","conf","state","tasks") if os.path.isdir(os.path.join(PEND,d))]
    tar_ok = False
    if dirs:
        rc,out = sh("cd "+PEND+" && tar czf "+tarf+" "+" ".join(dirs)+" 2>&1", 60)
        tar_ok = (rc==0 and os.path.exists(tarf))
    size = os.path.getsize(tarf) if os.path.exists(tarf) else 0
    return {"ok": tar_ok, "file": tarf if tar_ok else "", "size": size, "packed_dirs": dirs}

r = backup()
chk("备份成功", r["ok"])
chk("文件存在", os.path.exists(r["file"]))
chk("大小>0", r["size"]>0, str(r["size"])+"B")

print("\n[6] 数据库名清洗")
def clean_db_name(n):
    return re.sub(r"[^A-Za-z0-9_]","",n)[:40]
chk("正常名通过", clean_db_name("myapp")=="myapp")
chk("特殊字符清除", clean_db_name("my-app;drop")=="myappdrop")
chk("长度截断", len(clean_db_name("a"*60))==40)

print("\n[7] 站点名清洗")
def clean_site(n):
    return re.sub(r"[^A-Za-z0-9_-]","",n)[:40]
chk("正常名", clean_site("blog")=="blog")
chk("路径穿越阻止", clean_site("../../etc")=="etc")
chk("下划线保留", clean_site("my_site")=="my_site")

shutil.rmtree(PEND)
print("\n"+"="*52)
print(" 结果: %d 通过, %d 失败" % (PASS,FAIL))
print("="*52)
exit(0 if FAIL==0 else 1)
