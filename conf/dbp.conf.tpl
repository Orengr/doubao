; dbp.conf — supervisord 配置模板
; 变量 __PEND__ / __NODE__ 会在 install.sh 中被替换
;
; 说明：所有程序 autostart=true autorestart=true，
; 即使沙箱被回收，重装配置后也会自动全部拉起。

[program:dbp-ctl]
command=__NODE__ __PEND__/bin/dbp-ctl.py
directory=__PEND__
user=user
autostart=true
autorestart=true
startsecs=5
startretries=999
stopasgroup=true
killasgroup=true
stdout_logfile=__PEND__/log/ctl.log
stderr_logfile=__PEND__/log/ctl.err
environment=PEND="__PEND__",CTL_PORT="17800",PANEL_PORT="18090",BIND="127.0.0.1"

[program:dbp-1panel]
command=/usr/local/bin/1panel
directory=__PEND__/1panel-data
user=root
autostart=true
autorestart=true
startsecs=30
startretries=999
stopasgroup=true
killasgroup=true
stdout_logfile=__PEND__/log/1panel.log
stderr_logfile=__PEND__/log/1panel.err
environment=PANEL_BASE_DIR="__PEND__/1panel-data"

[program:dbp-frpc]
command=__PEND__/frp/frpc -c __PEND__/frp/frpc.toml
directory=__PEND__/frp
user=user
autostart=true
autorestart=true
startsecs=8
startretries=999
stopasgroup=true
killasgroup=true
stdout_logfile=__PEND__/log/frpc-sv.log
stderr_logfile=__PEND__/log/frpc-sv.err

[program:dbp-watch]
command=__NODE__ __PEND__/bin/dbp-watch.py
directory=__PEND__
user=user
autostart=true
autorestart=true
startsecs=5
startretries=999
stdout_logfile=__PEND__/log/watch.out
stderr_logfile=__PEND__/log/watch.err
environment=PEND="__PEND__",CTL_PORT="17800",PANEL_PORT="18090"
