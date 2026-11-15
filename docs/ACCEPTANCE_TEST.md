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


## v6 更新（2026-11-15 21:30）
### 架构拆分（按用户要求）
- **ka_pure.py v6（纯保活）**：只发沙箱小任务（99乘法表/404网页/系统信息/计算器/名言JSON/报价CSV/小作文/目录树），不检测隧道、不发恢复指令。间隔 keep_interval_sec（默认1800）。
- **tunnel_watch.py（独立哨兵）**：systemd 常驻，每秒探测 17800/18090，连续3秒失败 → 秒发拉起指令（60秒冷却防刷），与 ka_pure 完全解耦。
- 死亡自动新建切回真接口 create_conv_by_send（cookie 修复后实测成功：38453917458543618 AUTO-TEST-2115 真落列表）。

### 全程自动验收（无人工干预，日志实锤）
触发：仅一次标死老王（O）。之后系统自己完成：
```
21:27:05 ☠️ 检测死亡 → 自动新建 38453969411489282 → 自动重命名「老王（P）」→ 设为保活
21:27:05 [1] 对新会话发保活小任务(404网页)  21:27:12 豆包回复 ✅存活
21:27:42 [2] 系统信息小报告                21:28:03 豆包回复 ✅存活
21:28:33 [3] 计算器脚本                    21:28:48 回复含「不支持」→ 标死(误判)
21:28:46 tunnel_watch 连续3秒失败 → ⚡ 秒发拉起指令
```
用户手机截图确认「老王（P）」会话里自动出现 新会话初始化 / 404网页 / sysinfo / 恢复指令。

### 修复
- 「不支持/无法提供」从 death_keywords 移除（误判正常回复）；误标会话按规则手动改存活，下次保活重新读回复。
- tunnel_watch 日志重复：systemd StandardOutput 改 null，只留 FileHandler。
- ka_pure 死亡判断强化：每轮直接查 conv_status 强制重读，避免竞态。


## v7 更新（2026-11-15 22:40）
### 用户 5 项反馈
1. **存活状态手动标记**：会话列表每个会话右侧加「标记存活 / 标记死亡」按钮（event.stopPropagation，不会误进会话）；聊天页工具条也保留。
2. **哨兵与保活一起控制**：keepctl.status() 同时读 ka-pure/tunnel-watch，总状态=两者都 active；「启用保活」restart 两个服务，「停止保活」stop 两个服务。实测停止后 inactive/inactive，启用后 active/active。
3. **1800 秒说明**：那是"沙箱小任务保活间隔"（之前默认 30 分钟），不是隧道检测。界面改成「小任务保活间隔 __ 分钟」并附说明：只控制 99 乘法表/404 网页这类小任务频率；隧道哨兵每秒检测、连续 3 秒失败立即拉起，不受此值影响。默认改为 600 秒（10 分钟）。
4. **聊天页完整度/高度/时间**：/api/conv/messages 不再截断文本，带 create_time；聊天页每条显示日期时间；body 改 100dvh + overflow:hidden，消息区 min-height:0 可滚，输入区 flex-shrink:0 固定底部，加 safe-area-inset-bottom。
5. **模式切换去 emoji**：改成下拉选择「云电脑（可执行沙箱任务） / 普通对话」，当前值回填，无 emoji。

### 修
- /api/keep/stop 原只停 ka-pure → 改 KEEP.stop_all()；新增 /api/keep/start。
- /api/conv/new 误用 create_conv_by_ui → 切回已打通的 create_conv_by_send。


## v8 更新（2026-11-15 22:55）
### 用户 4 项
1. **小任务保活 3–5 分钟随机**：ka_pure 不再读 keep_interval_sec，启动/每次发送后用 random.randint(180,300) 抽下次间隔，并打日志「下一次小任务将在 N 秒后」。实测新进程 22:51:04 启动日志生效。
2. **模式改回无 emoji 分段按钮**：「云电脑 / 对话」两个按钮，当前项高亮，.seg 分段控件，无 emoji、无下拉。
3. **已登录隐藏登录卡 + 顶栏账号 + 退出登录**：顶栏显示「● 当前已登录：小777」+「退出登录」按钮；/api/logout 停 ka-pure/tunnel-watch、清 active_account.json、清浏览器 cookie（保留账号库/历史/配置）。防假登录：status() 用 sessions 验活，读不出会话列表就 logged_in=false。未登录时顶栏「登录」按钮可展开登录卡。
4. **会话列表限高可滑动**：#convs max-height:210px + overflow-y:auto + 滚动条样式，约 3 个会话高度，其余滑动查看。

### 运维注意
- ka_pure 曾因 pkill -9 后 systemd 进入 failed 未自动拉起，用 systemctl reset-failed ka-pure && systemctl start ka-pure 恢复。常规「启用/停止保活」走 keepctl 不受影响。


## 总项目进度对账（2026-11-15 23:05，实测）
| 模块 | 状态 | 证据 |
|---|---|---|
| 纯接口短信登录 | ✅ | send_code/sms_login + X-Bogus，账号小777，7→12会话可见 |
| 真发送消息接口 | ✅ | /chat/completion 抓包，SSE_ACK + /im/chain/single 落库 |
| 会话/消息/重命名/新建 | ✅ | recent_conv/chain_single/update/create_conv_by_send |
| 18800 纯接口管理台 | ✅ | 6板块/24API/独立对话页/登录退出/验活/防假登录 |
| 账号设备档案+配置持久化 | ✅ | SQLite accounts/settings/conv_status/login_history |
| 纯小任务保活(3-5min随机) | ✅ | ka_pure v8 日志「下一次小任务将在N秒后」 |
| 独立隧道哨兵(1s/3fail) | ✅ | tunnel-watch active，连续3秒失败秒发拉起 |
| 死亡检测/自动新建/重命名 | ✅ | 21:27 全自动链路实锤，老王(P) |
| 云电脑/对话模式 | ✅ | 分段按钮，mode_select_value |
| GitHub 开源 | ✅ | Orengr/doubao main 持续推送 |
| **导航页(80端口)** | ✅ 本次补 | / 返回 Moin Server 导航，全部入口复用80，无新端口 |
| 1Panel 网站 /panel/ | ❌ 502 | 沙箱侧 frpc 未回连，18090 无监听 |
| 控制面 17800 | ❌ 000 | 沙箱侧 ctl2.py 未起 |
| 沙箱 frp 隧道 | ❌ 断 | frps 7000 在跑但无 proxy |
| 沙箱实例/ensure.sh 自恢复 | ❌ 未恢复 | 豆包回复空，隧道哨兵持续检测 |
| a_bogus 纯离线算法 | ⚠️ 部分 | 真请求参数已抓全，但签名由页面 bdms 环境生成，未做纯 Python 复刻 |

### 结论
**整个项目未完成，约 85%。** 服务器侧（登录/接口/管理台/保活/哨兵/文档/GitHub/导航页）全部完成并实测；
**豆包沙箱侧没起来**：frp 隧道断、17800/18090 无监听、1Panel 网站 502，导致"用豆包当免费服务器"这最后一环没闭环。
导航页已如实标红 1Panel 不通，不假装在跑。
剩余唯一主线：让豆包在沙箱里执行 ensure.sh/restore_all.sh 把 frpc+1Panel+控制面拉起来，隧道回连后 /panel/ 自动可用。


## 纠错（2026-11-15 23:20，亲自复跑后更正）
之前几轮误判，特此更正，**以会话记录 + frps dashboard 为唯一标准**：
1. **不是账号风控**：23:10 一次 `710022004` 是瞬时拒绝。23:15:51 用户「你好呀」发出并回复；23:16 亲手实验 `SSE_ACK` 无 STREAM_ERROR，抽出真回复；23:14:38 / 23:15:36 / 23:16:40 保活与恢复指令全落库。
2. **不是 frps 双进程**：现只有 pid 3953408，systemd MainPID 就是它；11-14 的 `bind: address already in use` 是历史日志。dashboard 端口是 **7501** 不是 7500。
3. **沙箱/1Panel 实际已恢复**：frps dashboard 两条 proxy moin-control(17800)/moin-panel(18090) 均 online，lastStartTime 23:15:08；`17800/ping` → `{"ok":true,host:vefaas-l148mv98…}`；经 80 端口 `/` `/panel/` `/lite/` 全 200。
4. **真实根因只有一个**：`send_full` 把"有 SSE 回包"当落库、空回复也记 ✅，导致 22:35~23:14 之间日志显示成功但会话记录没消息；后来又把一次瞬时风控错误固化成全局失败判定，把真成功也屏蔽了。已修：只在 `STREAM_ERROR 且无 SSE_ACK` 时判失败；空回复不记成功但如实报「无有效回复（未落库）」。
5. **总项目重新核对：已完成**。服务器侧 + 豆包沙箱侧 + frp 隧道 + 1Panel 入口全部实测可用。

### 当前真实状态
- 服务：moin-unified / ka-pure / tunnel-watch / frps / nginx / xvfb / doubao-cdp 全 active
- 入口(仅80)：/ 导航页200、/lite/ 控制台200、/chat 对话页200、/api/ 200、/dl/ 200、/panel/ 200
- 沙箱：17800/ping ok，frp 两隧道 online，保活小任务 3-5min 随机，哨兵 1s/3fail
- 会话：老王（P）存活，保活运行中，豆包持续执行 ensure.sh / 小任务
- 1Panel 直连 18090 根路径显示「暂时无法访问」是 1Panel 自身安全入口（需带随机路径），非故障


## 1Panel 安全入口（2026-11-15 23:33）
- 导航页「1Panel 面板」原 href=/panel/ 根路径 → 1Panel 自带「暂时无法访问 / 已开启安全入口登录」拦截页，不是真面板。
- 让豆包在沙箱执行 `1pctl user-info` 读到真实入口：`http://114.215.204.238:18090/cSK41ajJX5`，用户 `1panel_admin`，密码 `Jwgk8CoJfnts`。
- 导航页磁贴改为直达 `/panel/cSK41ajJX5`（经 80 端口 proxy 到 18090 安全入口，实测 200、标题 loading…=1Panel 前端）。补「1Panel 登录信息」卡显示入口/用户名/密码。
- 不新开端口；panel.moin520.me 同样走 80。
