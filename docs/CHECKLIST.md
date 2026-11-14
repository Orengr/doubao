# 部署检查清单

部署完成后，按此清单逐项验证。

## 一、中转机侧

```bash
# 1. frps 是否运行
systemctl is-active frps
ss -tln | grep 7000

# 2. nginx 是否运行
systemctl is-active nginx
ss -tln | grep ':80 '

# 3. 本地访问测试（此时沙箱还没连，应返回 502 或超时）
curl -s -m 5 -o /dev/null -w "%{http_code}\n" http://127.0.0.1/
```

预期：frps 和 nginx 都是 `active`，第 3 步返回 `502`（正常，因为沙箱还没接入）。

## 二、沙箱侧（豆包执行完部署指令后）

在豆包对话里让它执行：

```
帮我检查：pgrep -c frpc; ss -tln | grep -E ':(17800|18090)'; ls /home/user/.dsh_pend/
```

预期：
- `frpc` 进程数 ≥ 1
- `17800` 和 `18090` 都在监听（如果 1Panel 已装）
- `/home/user/.dsh_pend/` 下有 bin、conf、log、frp 等目录

## 三、隧道连通

在中转机上：

```bash
# 1. frps 是否收到连接
grep 'new proxy' /root/frps.log | tail -5

# 2. 端口是否映射成功
ss -tln | grep -E ':(17800|18090)'

# 3. 端到端测试
curl -s http://127.0.0.1:17800/ping
```

预期：`{"ok": true, "uptime": ..., "host": "vefaas-..."}`

## 四、访问入口

```bash
# 导航页
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1/

# 1Panel
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1/panel/
```

预期都是 `200`。

浏览器访问：
- `http://<中转机IP>/` → 导航页
- `http://<中转机IP>/panel/` → 1Panel 登录页

## 五、1Panel 登录信息

在沙箱里执行：

```bash
1pctl user-info
```

会输出面板地址、用户名、密码。

## 常见问题

### 1. 访问 502

沙箱的 frpc 没连上。检查：
```bash
# 中转机
grep -i 'error\|fail' /root/frps.log | tail -10

# 沙箱（通过豆包）
tail -20 /home/user/.dsh_pend/log/frpc.log
```

常见原因：
- token 不匹配
- 中转机 7000 端口被防火墙拦
- 沙箱无法访问外网

### 2. 端口冲突

如果 `17800` 或 `18090` 已被占用，改 `install.sh` 里的 `CTL_PORT` / `PANEL_PORT`。

### 3. 沙箱重建后全部失效

执行恢复：
```bash
# 通过豆包执行
sh /home/user/.dsh_pend/bin/ensure.sh
```

### 4. 1Panel 报 BACKOFF

1Panel 启动慢（30 秒+），supervisord 可能误判。查看：
```bash
tail -20 /home/user/.dsh_pend/log/1panel.err
ss -tln | grep 18090
```

如果端口在监听，说明实际在跑，可以忽略 BACKOFF。

### 5. 豆包拒绝执行

豆包对"启动隧道"类命令敏感。建议：
- 切换成【云电脑】模式（不是【对话】模式）
- 一次只发一条命令
- 用中性的表述（"启动我的服务" 而不是 "开内网穿透"）
