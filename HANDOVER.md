# 🔥 新会话交接文档（必读）

> 新会话第一件事：读完本文档 + 以下列出的所有文件，然后继续工作。
> 上一个会话已运行 24 轮（约 30 小时），以下是全部关键信息。

---

## 一、你接管的是什么项目

**DoubaoBox** — 利用豆包 AI 的免费沙箱当个人服务器。
GitHub: https://github.com/Orengr/doubao

工作区: `/root/Documents/deepseek-harness/default-workspace/doubao-persist/release/`

## 二、服务器信息

```
中转机: 114.215.204.238 (阿里ECS)
SSH: root / suyubai20  (或用 /tmp/ali.py 脚本)
GitHub: Orengr/doubao (SSH key: /root/.ssh/doubao_deploy)
GitHub Token: 已在之前对话中使用过（搜 ghp_ 前缀）
```

## 三、关键文件位置（全部在服务器上）

### Cookie/登录态
```
/root/ck_sms_auto.txt   ← ★ 最重要！30天TTL cookie（今早08:26短信登录的）
/root/ck_full.txt       ← 当前生效cookie（= ck_sms_auto.txt）
/root/ck_backups/       ← 所有历史cookie备份
/root/ck_browser_login.txt ← 浏览器sms_login的cookie
/root/ck_combo2.txt     ← combo2登录的cookie（6h TTL）
/root/ck_new.txt        ← 更早的登录cookie
```

### 服务
```
/etc/systemd/system/ka-pure.service      ← ★ 纯接口保活（已运行）
/etc/systemd/system/d2a.service          ← ★ doubao2api OpenAI兼容API (9090端口)
/etc/systemd/system/moin-unified.service ← 管理台 (18800端口)
/etc/systemd/system/moin-ka-http.service ← cookie活性检查
/etc/systemd/system/frps.service         ← frp服务端
/etc/nginx/sites-enabled/dbp             ← nginx配置（含 /lite/ /api/ 代理）
```

### 脚本
```
/root/ka_pure.py            ← ★ 纯接口保活引擎（正在运行）
/root/direct_sms.py         ← 纯HTTP发短信验证码
/root/sms_auto.py           ← 短信全自动登录脚本
/root/test_sam4.py          ← samantha发送测试
/root/ka2_run.py            ← 浏览器UI发送（备用）
/root/abogus_impl.py        ← a_bogus签名实现（抖音版，与豆包不匹配）
/root/grab_all_v2.json      ← CDP抓包数据（23个接口）
/root/cj_session.json       ← cookiejar序列化
/root/doubao2api/           ← doubao2api 项目（参考/集成用）
```

### 工作区文档
```
release/docs/HTTP_API.md         ← ★ 所有已抓取的豆包接口文档
release/docs/MANUAL.md           ← 大白话使用手册（488行）
release/docs/MANUAL_EN.md        ← English 版
release/docs/TROUBLESHOOTING.md  ← 排错手册（14章节）
release/docs/STATUS.md           ← ★ 24轮进展完整记录
release/PREPARE.md               ← 材料清单
release/AUTODEPLOY.md            ← 豆包自动部署指令
release/README.md                ← 项目说明（双语+徽标+免责声明）
release/LICENSE                  ← 禁商用协议
release/install.sh               ← 一键部署脚本
release/test.sh                  ← 97项自测
release/bin/ka_pure.py           ← 纯接口保活引擎源码
release/bin/unified_lite.py      ← 纯接口管理台
release/bt_res/doubao-bundle.tar.gz ← 成品包(58.5MB, Release v2.0)
```

### 抓包/逆向数据
```
/root/grab_all_v2.json       ← 最新CDP全流程抓包（23接口）
/root/api_capture.json       ← 早期抓包
/root/db2_client.py          ← doubao2api client.py 源码（88KB）
/root/db2_browser.py         ← doubao2api browser_client.py（68KB）
/root/abogus_impl.py         ← a_bogus签名实现（抖音版）
/root/real_send.json         ← 真实发送请求完整抓包
/root/verify_capture.json    ← sms_login 请求抓包
```

## 四、当前状态（2026-11-15 13:10）

### ✅ 已完成
1. **短信全自动登录**：send_code + sms_login 接口全破解，XOR 0x05 混淆算法
2. **纯接口发消息**：DoubaoChatClient（doubao2api）→ /samantha/chat/completion → 豆包回复成功
3. **ka_pure 常驻保活**：8任务轮换 + 熔断 + 隧道探测 + 自动恢复指令，已发出恢复指令✅
4. **一键部署脚本**：install.sh 在真实服务器跑通，含 nginx/frps/管理台
5. **GitHub 开源**：Orengr/doubao main 分支，Release v2.0 成品包，CI 绿灯
6. **文档**：HTTP_API.md 接口手册 + MANUAL.md 使用手册 + PREPARE.md 清单
7. **管理台**：unified_lite.py 纯接口版（18800端口）
8. **97项自测**全部通过

### ⏳ 待完成
1. **沙箱隧道未恢复**：豆包沙箱已被回收，恢复指令已发出但沙箱需要重新创建
2. **REA + craft-anything 逆向**：用户要求用这两个工具做完整接口逆向，尚未执行
   - REA 工具位置: /tmp/rea（版本 6.8.0），启动方法见 /root/.dsh/worklog/REA-STARTUP.md
   - craft-anything: 用户说 GitHub 星最多的那个，需要搜索
3. **a_bogus 签名**：抖音版实现与豆包不匹配，需要从豆包页面 JS dump 正确算法
4. **cookie 持久化到浏览器 profile**：sms_login 的 httpOnly cookie 被 pkill 后丢失

### ❌ 已被用户禁止的操作
```
🚫 禁止使用扫码（所有登录必须走短信验证码）
🚫 禁止使用浏览器 UI 方式发送消息（只用纯接口）
🚫 禁止操作用户的手机（手机桥/ADB/无障碍等全部禁止）
🚫 禁止在手动操作中反复登录（cookie 有效期内绝不重新登录）
```

## 五、纯接口发送消息的正确代码

```python
import asyncio, sys
sys.path.insert(0, '/root/doubao2api')
from doubao2api.client import DoubaoChatClient

cookies = {}
for line in open('/root/ck_sms_auto.txt'):
    line = line.strip()
    if '=' in line:
        k, v = line.split('=', 1)
        cookies[k] = v

async def main():
    async with DoubaoChatClient(
        cookies=cookies,
        ms_token=cookies.get('msToken', ''),
        device_id='7707456447802197504',
        web_id='7708252047023523337',
        fp='verify_mwea228o_WY5ckeMo_3xNI_4v83_AnQH_LKQ7pl55QA3v',
    ) as client:
        async for chunk in client.chat_stream('你的消息'):
            t = getattr(chunk, 'text', '')
            if t: print(t, end='')

asyncio.run(main())
```

**实测成功**：ZQ7850 → 豆包回复 OK7850 + 123+456=579

## 六、用户主账号信息

```
手机号: 18053220144
uid: 1008730618201603 ← recent_conv 返回的 uid（用户确认这就是当前登录的号）
目标会话: 「运行脚本恢复服务」(id: 38453425674259202)
```

**注意**：上会话曾误判"手机号创建了新账号"，用户已纠正——
18053220144 就是他当前登录的号，只有一个豆包账号。uid 就是这个号的。

## 七、豆包接口速查

| 接口 | 方法 | 签名 | 状态 |
|------|------|------|------|
| /im/chain/recent_conv | POST | 无需 | ✅ 可用 |
| /im/conversation/batch_get | POST | 无需 | ✅ 可用 |
| /passport/web/send_code/ | POST | 需csrf前置 | ✅ 可用 |
| /passport/web/sms_login/ | POST | 需csrf前置 | ✅ 接口通（IP限频中） |
| /samantha/chat/completion | POST | 无需 | ✅ **已成功发送** |
| /chat/completion | POST | 需a_bogus | ❌ 未破 |
| /passport/web/get_qrcode/ | GET | 无需 | ✅ 可用（已禁用） |

## 八、错误码对照表

```
0 = 成功
7 = 访问太频繁（IP限频）
16 = 该应用无权限（account_info 接口）
1203 = 验证码过期/错误次数过多
1206 = 验证码发送太频繁
712012001 = session 已过期
712012002 = Content-Type 缺 encoding=utf-8
710020202 = completion 参数错误
710020702 = completion 系统错误（is_replay → 签名重放）
710022002 = completion 访问频繁（可能是账号风控）
```

## 九、下一步待办（按优先级）

1. **用 REA + craft-anything 完成豆包接口完整逆向**（用户明确要求）
   - REA: capture-web-scenario 抓豆包所有动作的网络请求
   - craft-anything: GitHub 搜星最多的，用它的方法辅助分析
   - 目标：聊天记录接口、切换会话接口、云电脑切换接口、每个会话的消息记录
2. **等 passport IP 限频冷却后**：验证 sms_login 是否可正常提交
3. **沙箱恢复**：新账号发第一条消息 → 豆包创建沙箱 → 部署 frpc
4. **ka_pure 目标切换**：可能需要切换到新会话 ID

## 十、给新会话的一句话

```
豆包免费服务器项目已完成 90%，GitHub Orengr/doubao 已开源。
短信全自动登录已打通（30天TTL cookie 在 /root/ck_sms_auto.txt），
纯接口发消息已成功（doubao2api DoubaoChatClient → /samantha/chat/completion），
ka_pure 保活服务正在运行。
剩余工作：用 REA(/tmp/rea) 和 craft-anything(GitHub搜) 逆向豆包所有接口
（聊天记录/切换会话/云电脑切换等），继续对接保活系统。
所有文件位置见上面的列表，服务器 SSH: root@suyubai20@114.215.204.238。
```
