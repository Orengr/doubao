# 18800 验收测试操作手册（2026-11-15 v2）

## 系统组成
| 组件 | 位置 | 作用 |
|---|---|---|
| moin_api_console.py v2 | 服务器 /root/, 端口 18800 | 网页管理台（纯接口，无扫码）|
| accounts_db.py | /root/ | SQLite：账号/设备档案/登录历史/保活会话映射 |
| login_api.py | /root/ | 纯接口短信登录：send_code + sms_login + X-Bogus 签名 + 导出 cookie/设备档案 |
| keepctl.py | /root/ | 保活控制：按账号档案选择会话、启停 ka_pure |
| inject_ck.py | /root/ | 把账号 cookie 注入 CDP 浏览器 |
| cloudmode.py | /root/ | 读取/设置云电脑模式（9=云电脑，0=对话）|
| boot_restore.py | /root/ + systemd doubao-boot.service | 开机恢复：注入 active 账号 cookie + 云电脑模式 |
| xvfb.service / doubao-cdp.service | systemd | Xvfb :99 + 非 headless Chromium CDP 9222 常驻 |
| doubao_send.py | /root/ | 经页面环境发真 /chat/completion（落库）|
| ka_pure.py | /root/ | 保活引擎，目标会话由 keepconf.json 决定 |

## 已验证接口
- 登录: send_code / sms_login（XOR 0x05 + bdms X-Bogus，页面环境）
- 真发送: POST /chat/completion（client_meta + content_block + option，SSE_ACK 落库）
- 读取: recent_conv(3200) / conversation_info(1110) / chain_single(3100)
- 验活: /api/alive → 7 会话
- 云电脑模式: mode_select_value=9，账号级 localStorage，不发独立切换接口；发消息时 option.general_task_param 生效（对话模式换成 model_config）

## 验收步骤（你来做）
1. 打开 http://114.215.204.238:18800 （或你的域名 /lite/）
2. 「① 登录」区：填手机号 18053220144 → 点「获取验证码」
3. 手机收码 → 填入「6 位验证码」→ 点「提交登录」
4. 首次登录会弹窗「配置保活会话」→ 选一个会话（不选=保活关闭）
5. 点「保存并启用保活」→ 自动：写账号库 + 登录历史 + 注入 cookie + 重启 ka_pure
6. 「② 当前账号 / 保活配置」显示：账号名、UID、保活会话、云电脑模式
7. 「③ 发送消息」明确标注发给哪个账号的哪个会话，下拉可改选
8. 「⑤ 消息记录」刷新 → 能看到刚发的消息和豆包回复（验收标准）
9. 「⑥ 历史登录」有记录；再次登录同账号默认沿用之前的保活会话，不弹窗

## 删凭证测试（你说的验收方式）
在服务器上执行后仍能网页登录：
```bash
python3 /tmp/ali.py "rm -f /root/ck_*.txt /root/doubao_accounts.db /root/active_account.json; systemctl restart moin-unified"
```
然后走上面 1-9 步。登录执行器会把新 cookie 存成 /root/ck_<uid>.txt 并重建账号库。

## 铁律
- 验收只认 /im/chain/single 里查得到的消息
- cookie 有效期内绝不重新登录（单点会话）
- 真凭证文件不进 GitHub（.gitignore 已排除）


## v3 更新（2026-11-15 20:20）
### 已实现并实测
1. **保活状态显示在开关旁**：「② 账号/保活开关」标题与按钮行各一处，●运行中/●已停止
2. **会话列表可点开**：点任意会话 → 弹窗显示历史聊天记录 + 发送框 + 实时等豆包回复；保活会话排第一、绿色框；外部"发送消息/消息记录"卡已删除
3. **启用保活立即发送**：keepctl.activate 触发 ka_once.py，点完马上发一条保活自检并返回豆包回复（不再等 30 分钟）
4. **会话死亡/存活标记**：conv_status 表，列表红色死亡/绿色存活
5. **死亡检测**：发送后读 SSE 回复，命中「不能执行/拒绝执行/高风险/高危操作…」→ 自动标记死亡（只标一次）、不再保活；实测 20:13:55 命中「高风险」自动标记成功
6. **手动改存活**：会话弹窗「标记存活」，下次保活重新读回复，无拒绝词则继续
7. **死亡自动新开会话**：设置项 auto_new_on_dead，默认 0（关），用户开启才做
8. **所有开关写数据库**：settings 表（auto_new_on_dead / rename_prefix / rename_style / rename_counter / keep_interval_sec / wake_interval_sec / cloud_mode / death_keywords），换账号登录记住
9. **重命名接口**：POST /alice/conversation/update {conversation_id,name}（实测成功）；新会话命名前缀+后缀(A/B/C 或 1/2/3)可配置，预览「老王（D）」
10. **云电脑模式**：☁️云电脑 / 💬对话 双按钮，当前选中高亮
11. **网页发消息+实时回复**：/api/conv/send 返回豆包 reply，实测成功

### 已知限制（如实标注）
- 新建会话接口：豆包新建会话由"发首条消息"触发，纯接口 create 未打通（/im/conversation/create cmd1100 参数错误、need_create_conversation 报 710020202）。管理台「➕新建会话」会明确提示：请在豆包页面新建，管理台自动读取后可重命名/设保活。因「死亡自动新开」默认关闭，不影响主流程。
- 4/5（App 化、多会话同时保活）为后续规划，未实现。

### 抓到的新接口
- /alice/conversation/update（重命名）
- /im/conversation/create cmd=1100 uplink=create_conv_uplink_body（参数未全破）
- /im/conversation/modify（模型配置，非重命名）
- 云电脑模式：无独立切换接口，账号级 localStorage mode_select_value=9，发消息时 option.general_task_param 生效


## v4 更新（2026-11-15 20:55）
### 用户 3 条要求
1. **死亡自动新建开关打开测试** → auto_new_on_dead=1 已开；实测 20:53:27 死亡后自动接管会话并重命名「老王（O）」、设为保活
2. **重命名是死亡新建后自动命名**（老王 + A/B/C 递增）→ next_conv_name() 已实现；命名配置(前缀/letter|number/计数)全在 settings 表
3. **会话点开改仿豆包独立对话页** → /chat?cid=... 独立页：返回按钮(‹)、消息气泡(我蓝/豆包灰)、底部输入框+发送、工具条(存活/死亡/重命名/设保活/刷新)、viewport 手机适配；首页列表点击跳该页

### 如实标注
- 豆包"程序化新建会话"接口未打通：/im/conversation/create cmd1100 参数错误、need_create_conversation 经页面 fetch 只回 SSE_ACK 但会话不落列表、React 受控 textarea 注入不过校验。
- 因此"死亡自动新建"实现为**自动接管**：从会话列表挑一个存活非死亡会话 → 按命名配置重命名 → 设为保活。用户在豆包手动新建会话后系统自动接管，行为等价。不做假成功。
- 实测日志：20:53:27 启动→检测死亡→自动接管 38453968823188994 老王（O）→设为保活

### 新建会话真实 body（抓包成果，供后续继续破）
POST /chat/completion，client_meta.local_conversation_id="local_<ts>" + conversation_id:"" + option.need_create_conversation:true + conversation_init_option/conversation_init_ext/conversation_mode:2/model_config/aggregate_params/ext。
真人路径：导航 /chat → textarea[data-testid=chat_input_input] → 点 [data-testid=chat_input_send_button]。


## v5 更新（2026-11-15 21:05）
### 用户 3 个问题
1. **保活会话名与列表不一致** → status() 以会话列表实时名为准；根因是浏览器 cookie 被测试导航冲掉导致重命名请求报「登录已过期」，rename() 现在先重新注入完整 cookie 再改名。实测列表与保活都显示「老王（O）」
2. **会话点进去 502** → nginx 只代理 /lite/ 和 /api/，/chat 被 location / 转给已挂的 17800。已加 location /chat 转 18800 并 reload nginx，实测经 nginx /chat 200
3. **保活功能测试按钮** → 「🧪 保活功能测试」：点击后后台 worker 按 3s「你好」/7s「你好你好」/10s「你好呀」三次发送，前端每 1.5s 轮询显示进度、结果、豆包回复、死亡判定。实测三条全部 ok:true + 真回复 + death:null

### 根因记录
- 浏览器 CDP cookie 数量从 43 掉到 15（反复导航 /chat 新对话页冲掉登录态）→ 页面 fetch 类接口（重命名/新建）报 710012001，但 curl 直连 cookie 仍有效。修法：页面环境操作前跑 inject_ck.py 重新注入。
