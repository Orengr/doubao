# 豆包沙箱 · Moin 面板（自制）

在豆包工作区（rootfs 易重置、无 systemd、无 Docker）里跑一套**自研服务器面板**，替代宝塔/1Panel。

## 为什么自制

宝塔和 1Panel 都重度依赖 Docker / systemd，而豆包沙箱：
- `CapEff=0`、`unshare` 被禁 → **Docker 起不来**
- `systemctl is-system-running → offline` → 面板自启失效

所以本项目直接自己做面板 + agent，**零 Docker 依赖**，深度适配沙箱。

## 架构

```
浏览器 → 服务器 nginx(80) → 18800 管理台/面板
                              ↓
                        frp 隧道(17801)
                              ↓
                       沙箱 17802 agent → 系统/文件/MySQL/PHP
```

| 组件 | 位置 | 作用 |
|---|---|---|
| moin_api_console.py | 服务器 18800 | 面板 UI + 管理台 + API 代理 |
| sbx_agent.py | 沙箱 17802 | 系统概览/进程/文件/站点/数据库/容器/终端 |
| sbx_guard.py | 服务器 systemd | 实例重建自动恢复 agent+隧道 |
| ka_pure.py | 服务器 | 纯小任务保活（60-90秒，维持沙箱活跃）|
| tunnel_watch.py | 服务器 | 隧道哨兵（每秒探测，连续5秒失败即拉起）|

## 面板功能（11 项）

**监控**：概览（CPU/内存/磁盘环形图，3秒实时刷新）、服务健康（6 项探测）
**建站**：网站（一键建站+自动 nginx vhost）、数据库（MySQL 建库/查表）、FTP 账户
**运维**：文件管理（浏览/读文件）、计划任务（cron）、进程（Top40）、容器应用（proot 隔离）、备份（数据打包+mysqldump）、终端（沙箱内执行）

## 一键部署

```bash
# 沙箱内执行
sh install_all.sh
```

自动完成：系统依赖(libaio/libzip/libncurses) → MySQL 8.0 解压+初始化 → PHP 8.1 解压 → nginx 检查 → 生成启动脚本 → 启动全部服务 → 汇总报告。

**预编译包**需放在 `$PEND/pkg/`：
- `mysql-8.0.40-linux-glibc2.17-x86_64.tar.xz`（820M）
- `php81-prebuilt.tar.xz`（49M）

## 访问

```
http://<服务器IP>/panel      面板
http://<服务器IP>/lite/      管理台（登录/保活）
http://<服务器IP>/           导航页
```

全部走 **80 端口**，无新增公开端口。

## 沙箱重置恢复

`sbx_guard` 守护会自动检测实例重建并恢复。手动恢复：
```bash
sh $PEND/bin/start_all.sh
```

数据全在持久卷 `/home/user/.dsh_pend`（10T）：`server/`（MySQL/PHP）、`www/`（站点）、`pkg/`（安装包）、`state/`、`log/`。

## 保活策略（重要）

| 参数 | 值 | 说明 |
|---|---|---|
| 发送间隔 | **240-360 秒**（4-6 分钟） | 60 秒会撞限流，实测 380 条后账号被封 |
| 失败退避 | +120s / 次，上限 900s | 越失败越发 = 越限流 |
| 隧道探测 | 每秒，**连续 5 秒**失败才拉起 | 避免抖动误判 |
| 消息内容 | 极简短句 | 长命令易触发内容审核 |

**教训**：曾把保活设成 60-90 秒，连续发 380 条后账号进入 `710022004 rate limited`，沙箱随即被回收。详见 [docs/12-限流与保活教训.md](docs/12-限流与保活教训.md)。

## 已知限制

- **Docker 不可用**（沙箱内核能力限制），容器化用 `proot` 替代
- 实例可能被平台回收，重建后 `sbx_guard` 自动恢复（约 20-30 秒）
- 不使用 cloudflared（与 frp 重复，已停用）


---

## 📚 文档导航

### 给豆包/AI 读的（自动部署）

| 文档 | 用途 |
|---|---|
| **[AUTODEPLOY.md](AUTODEPLOY.md)** | **豆包自动部署总控指令**（让它读这个） |
| [docs/11-部署指令卡.md](docs/11-部署指令卡.md) | 可直接复制粘贴给豆包的指令片段 |
| [docs/10-豆包助手指令.md](docs/10-豆包助手指令.md) | 豆包助手常用指令集 |
| [docs/09-额度与执行通道.md](docs/09-额度与执行通道.md) | **如何避免额度不足** |
| [QUICKSTART.md](QUICKSTART.md) | 3 分钟快速开始 |
| [PREPARE.md](PREPARE.md) | 部署前准备清单 |

### 给人读的

| 文档 | 用途 |
|---|---|
| [docs/MANUAL.md](docs/MANUAL.md) | 大白话使用手册 |
| [docs/HTTP_API.md](docs/HTTP_API.md) | 豆包接口速查 |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | 排错手册 |
| [docs/STATUS.md](docs/STATUS.md) | 开发进展记录 |
| [docs/14-项目完成度.md](docs/14-项目完成度.md) | **当前进度与 46 项实测记录** |
| [docs/13-频率限制实测.md](docs/13-频率限制实测.md) | 限流阈值与保活节奏依据 |

### 一句话部署

把这句话发给豆包：

```
请读取 https://raw.githubusercontent.com/Orengr/doubao/main/AUTODEPLOY.md 并按它执行全自动部署
```
