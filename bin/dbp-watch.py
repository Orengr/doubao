#!/usr/bin/env python3
"""
dbp-watch.py — 沙箱内看护（不依赖外部）

每秒检查：
  - 控制面 :17800 是否响应
  - 1Panel :18090 是否响应
  - frpc 进程是否存在
任一异常 → 自动拉起（不写死重启命令，全部走本地路径）

由 supervisord 托管，即使被 ELKEID 清理也会自动重启本看护。
"""
import os
import subprocess
import time
import socket
import logging

PEND = os.environ.get("PEND", "/home/user/.dsh_pend")
LOG = os.path.join(PEND, "log", "watch.log")
CTL_PORT = int(os.environ.get("CTL_PORT", "17800"))
PANEL_PORT = int(os.environ.get("PANEL_PORT", "18090"))

os.makedirs(os.path.dirname(LOG), exist_ok=True)
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.FileHandler(LOG, encoding="utf-8")])
log = logging.getLogger("watch")


def port_open(port, host="127.0.0.1", timeout=2):
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False


def proc_alive(name):
    try:
        r = subprocess.run(["pgrep", "-x", name], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def supervisor_start(prog):
    try:
        r = subprocess.run(["supervisorctl", "start", prog],
                           capture_output=True, text=True, timeout=20)
        return r.returncode == 0
    except Exception:
        return False


def main():
    log.info("=" * 44)
    log.info("dbp-watch 启动，每 5 秒巡检")
    log.info("=" * 44)
    n = 0
    fails = {"ctl": 0, "panel": 0, "frpc": 0}

    while True:
        n += 1
        time.sleep(5)

        # 控制面
        if not port_open(CTL_PORT):
            fails["ctl"] += 1
            if fails["ctl"] >= 3:
                log.warning(f"[{n}] 控制面不通 {fails['ctl']} 次，尝试拉起")
                supervisor_start("dbp-ctl")
                fails["ctl"] = 0
        else:
            fails["ctl"] = 0

        # 1Panel
        if not port_open(PANEL_PORT, timeout=3):
            fails["panel"] += 1
            if fails["panel"] >= 3:
                log.warning(f"[{n}] 1Panel 不通 {fails['panel']} 次，尝试拉起")
                supervisor_start("dbp-1panel")
                fails["panel"] = 0
        else:
            fails["panel"] = 0

        # frpc
        if not proc_alive("frpc"):
            fails["frpc"] += 1
            if fails["frpc"] >= 2:
                log.warning(f"[{n}] frpc 不在，尝试拉起")
                try:
                    frpc = os.path.join(PEND, "frp", "frpc")
                    toml = os.path.join(PEND, "frp", "frpc.toml")
                    if os.path.exists(frpc) and os.path.exists(toml):
                        subprocess.Popen([frpc, "-c", toml],
                                         stdout=open(os.path.join(PEND, "log", "frpc.log"), "a"),
                                         stderr=subprocess.STDOUT,
                                         start_new_session=True)
                except Exception as e:
                    log.error(f"拉起 frpc 失败: {str(e)[:80]}")
                fails["frpc"] = 0
        else:
            fails["frpc"] = 0

        if n % 60 == 0:
            log.info(f"[{n}] 巡检中 ctl={port_open(CTL_PORT)} "
                     f"panel={port_open(PANEL_PORT)} frpc={proc_alive('frpc')}")


if __name__ == "__main__":
    main()
