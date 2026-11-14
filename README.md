# DoubaoBox · 豆包沙箱免费服务器

[![Self Test](https://img.shields.io/github/actions/workflow/status/Orengr/doubao/test.yml?branch=main&label=tests)](https://github.com/Orengr/doubao/actions)

**语言 / Language**: [简体中文](README.md) | [English](docs/en/MANUAL.md)
[![License](https://img.shields.io/badge/license-禁商用·个人学习测试-red.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![Shell](https://img.shields.io/badge/shell-bash-green.svg)](https://www.gnu.org/software/bash/)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)]()
[![Status: Beta](https://img.shields.io/badge/status-beta-orange.svg)](docs/STATUS.md)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/Orengr/doubao/pulls)
[![Self Test](https://img.shields.io/badge/self%20test-88%20passed-success.svg)](test.sh)

在豆包沙箱里跑出一个**带 1Panel 面板的免费服务器**，数据存在 10T 持久卷，沙箱重建后自动恢复。

> 本项目基于 `Orengr/doubao-bt-deploy` 重构。原版用宝塔 + 编译 PHP/MySQL，安装耗时长、额度容易耗尽。本版改用 **1Panel（Go 单二进制，2 分钟装完）**，并加入自动保活与自愈机制。

---

## 快速开始

### 准备

一台**常驻的中转机**（任意 VPS / 免费容器，1 核 512M 够用）。

> 中转机只做流量转发和控制，**不存你的任何网站数据**。

### 部署

```bash
# 在中转机上执行
bash install.sh
```

按提示输入中转机公网地址即可。脚本会：
1. 装 frps（frp 服务端）
2. 配 nginx 分流
3. 生成一段**发给豆包的部署指令**

然后把生成的指令复制给豆包（**记得切到「云电脑」模式**），它会自动在沙箱里装好 frp 客户端。

### 访问

```
http://<中转机IP>/          导航页
http://<中转机IP>/panel/    1Panel 面板
```

1Panel 初始账号密码在沙箱里执行 `1pctl user-info` 查看。

---

## 架构

```
用户浏览器
    ↓
中转机（nginx + frps）
    ↓ frp 隧道（沙箱主动连出）
豆包沙箱
    ├─ dbp-ctl      :17800   控制面（状态 + 1Panel 反代）
    ├─ 1Panel       :18090   面板
    ├─ dbp-watch             自愈看护
    └─ frpc                  隧道客户端
```

**数据全部在 `/home/user/.dsh_pend/`**（10T 持久卷），沙箱重建不丢。

---

## 中转机是谁的机器？

**中转机 = 运行 `install.sh` 的那台机器，也就是使用者自己的机器。**

```
你部署    → 你的中转机 → 你的沙箱
别人部署  → 他的中转机 → 他的沙箱
```

代码里没有任何硬编码的服务器地址。`FRPS_ADDR` 在部署时自动检测
（或由使用者输入），所有下载/访问地址都基于这个变量生成。

**别人部署不会经过你的服务器，也不需要你的任何授权。**

## 为什么需要中转机

豆包沙箱**没有公网 IP**，只能主动向外连接。中转机提供一个固定入口，把流量转进沙箱。

中转机可以换成：
- 任意 VPS（1 核 512M 够用）
- fly.io / Koyeb 免费额度
- 任何有公网 IP 的机器

---

## 核心组件

| 文件 | 作用 |
|---|---|
| `install.sh` | 中转机一键部署 |
| `bin/dbp-ctl.py` | 沙箱控制面（状态 + 面板反代） |
| `bin/dbp-watch.py` | 自愈看护（进程掉了自动拉起） |
| `bin/install-1panel.sh` | 装 1Panel 到持久卷 |
| `bin/ensure.sh` | 恢复入口（幂等，可反复执行） |
| `conf/dbp.conf.tpl` | supervisord 配置模板 |
| `web/index.html` | 统一导航页 |

---

## 稳定性说明

### 已知限制

豆包沙箱是**临时执行环境**，有几个硬限制：

| 限制 | 应对 |
|---|---|
| 沙箱 2-5 分钟可能重建 | supervisord 托管 + `ensure.sh` 幂等恢复 |
| ELKEID 清理 setsid 进程 | 用平台 supervisord，不用 setsid |
| `/opt` 是 overlay，重启丢失 | 配置存持久卷，重建后自动装回 |
| 服务端可能吊销登录态 | 需人工扫码（**无法绕过**） |

### 自动恢复

`dbp-watch.py` 每 5 秒检查控制面、1Panel、frpc，异常自动拉起。

沙箱完全重建后，跑一次 `ensure.sh` 即可全部恢复：

```bash
sh /home/user/.dsh_pend/bin/ensure.sh
```

---

## 登录态维护

豆包网页需要登录才能操作。本项目提供：

- **扫码登录页**（首次）
- **Cookie 健康检查**（每 30 分钟）
- **掉线自动生成二维码**

### 关于登录：唯一的人工步骤（重要）

**开源版对普通用户的要求：**
```
1. 一台有公网 IP 的机器（任意 VPS / 免费容器）—— 必需
2. 一个豆包账号 —— 必需
3. 首次扫一次码 —— 必需
```

**不需要手机 root、不需要 ADB、不需要无障碍、不需要虚拟屏。**
扫码用任意设备上的豆包 App 都行，一次即可。

⚠️ **session 只能通过扫码或手机验证码获得，技术上无法绕过。**

这是字节服务端的安全设计，不是本项目的缺陷。开发过程中实测过 21 种
「免扫码」方案（cookie 注入、SSO/JWT 换票、OAuth、设备桥、虚拟屏），
全部被服务端拒绝。详见 [踩坑记录](docs/TROUBLESHOOTING.md)。

**本项目能做到的最好自动化：**
```
用户扫一次码
  ↓ 自动：保存 cookie → 解除熔断 → 拉起服务 → 恢复保活
  ↓ 自动：renew-activator 持续续期（6小时~30天 TTL 自适应）
  ↓ 只要保持活跃，长期不再需要扫码
```

> 若需完全无人值守，可考虑改用真正的免费容器平台
> （fly.io / Koyeb 等），它们不需要豆包登录态。

已实测失败的方案（不要浪费时间）：
- 用 `bd_sso_hi3jfd`（有效期 1 年）换 session → 服务端拒绝
- 用 `LARK_SUITE_ACCESS_TOKEN`（JWT）换 session → 服务端拒绝
- 把上述 token 作为 Cookie/Header 发送 → `710012001`
- 解密 profile 里的加密 cookie 后注入 → 会话已过期

**为什么**：豆包的 session 和 SSO 是两套独立体系，SSO 有效不代表 session 有效。
session 过期后服务端会拒绝一切本地凭据，只有重新认证能解决。

**减缓措施**（本项目已实现）：
`renew-activator.py` 在剩余 90 分钟时就开始续期，而不是等到过期边缘。
只要浏览器保持活跃，session 会持续滚动延长，不需要频繁扫码。

---

## 与原版差异

| 项目 | 原版 | 本版 |
|---|---|---|
| 面板 | 宝塔（Python，重） | 1Panel（Go，轻） |
| 安装耗时 | MySQL 3-8min + PHP 20-40min | **约 2 分钟** |
| 保活 | 无 | 自动保活 + 掉线检测 |
| 隧道 | cloudflared / serveo（会断） | frp 自建（稳定） |
| 恢复 | 手动跑脚本 | 幂等 ensure.sh + 看护 |

---

## 系统自检

部署后访问 `http://<中转机IP>/`，页面底部有「系统自检」区块，显示：
- 控制面运行时长
- 1Panel 状态
- frpc 进程
- 持久卷挂载
- 磁盘空间
- supervisord 托管

也可以直接调接口：
```bash
curl http://<中转机IP>/health
```

返回每项的 `ok` 与 `detail`，全绿表示系统正常。

## 查看系统状态

```bash
bash bin/status.sh
```

一条命令显示：中转机服务、监听端口、登录状态、沙箱隧道、最近日志。

## 自测

```bash
bash test.sh
```

验证 88 项，覆盖：
- 语法检查（10 项）
- 目录结构（8 项）
- 关键逻辑（6 项）
- 控制面启动（4 项）
- 配置生成（2 项）
- 健壮性（6 项）
- 端到端接口（7 项）
- 防刷屏逻辑（7 项，含熔断冷却）
- 续期时机（6 项）
- healthcheck（3 项）
- install-1panel（5 项）
- ensure 兜底（4 项）
- 熔断自愈（2 项）
- 登录自动恢复（3 项）
- 安全运维（3 项）
- 状态总览（3 项）
- CI 配置（2 项）

## 文档

- [快速开始](QUICKSTART.md) — 5 分钟上手
- [部署检查清单](docs/CHECKLIST.md) — 逐项验证
- [踩坑记录](docs/TROUBLESHOOTING.md) — 所有已知问题与解法
- [项目状态](docs/STATUS.md) — 已完成/待办

## 关于豆包额度

本项目把部署耗时从原版的 30+ 分钟压到约 2 分钟，
但豆包沙箱本身的**重建/回收由平台控制**，本项目无法保证沙箱永不过期。

建议：
- 用最小化任务保活（本项目已内置 8 种轻量任务轮换）
- 重要数据务必放 `/home/user/.dsh_pend/`（10T 持久卷，重建不丢）
- 若豆包策略收紧导致额度快速消耗，请降低保活频率

## ⚠️ 免责声明

1. **本项目仅供个人娱乐、技术学习与测试使用**，不含任何攻击、入侵、
   侵权或违法意图。
2. 本项目不提供任何明示或默示的担保，使用者需自行承担使用产生的
   全部风险与后果。
3. 本项目依赖的第三方服务（豆包 / 字节跳动）的所有规则、额度与政策
   由其官方制定，本项目无法控制。使用前请阅读并遵守其服务条款。
4. 使用者应确保自己的使用行为符合所在地法律法规。**因违规使用导致的
   一切责任由使用者本人承担，与本项目作者无关。**
5. 如本项目内容涉及您的合法权益（包括但不限于著作权、商标权），
   请通过 Issue 联系，我们将在确认后 24 小时内处理（删除或修改）。
6. **禁止将本项目用于任何商业用途或违法活动**，详见 [LICENSE](LICENSE)。

## 许可

**禁止商用**。仅限个人学习、测试与非商业性娱乐用途。

- 严禁出售、收费部署、用于盈利性产品
- 严禁违法用途
- 严禁去除署名
- 完整条款见 [LICENSE](LICENSE)
