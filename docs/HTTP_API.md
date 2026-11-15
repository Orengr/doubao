# DoubaoBox · 豆包网页版纯 HTTP 接口手册（抓包实测）

> 本文档记录 2026-11-14 实测打通的豆包网页版接口，纯 HTTP（urllib/requests）可调，
> 不依赖浏览器。是 v3 保活引擎（ka_http）的技术基础。

## 通用要求

```
Content-Type: application/json; encoding=utf-8    ← 必须带 encoding=utf-8！
                                                  缺了会报 712012002「不支持编码类型」
Cookie: <ck_full.txt 全部 cookie，分号连接>
User-Agent: 浏览器 UA（带 HeadlessChrome 字样也可以）
Referer: https://www.doubao.com/chat/<会话ID>
```

URL 通用 query：`version_code=20800&language=zh&device_platform=web&aid=497858&real_aid=497858&pkg_type=release_version`

## 已验证接口

### 1. 会话列表 POST /im/chain/recent_conv
```json
{"cmd":3200,"uplink_body":{"pull_recent_conv_chain_uplink_body":{
  "conv_version":0,"limit":50,
  "filter":{"conversation_type":[],"project_filter":0,"device_filter":1},
  "message_count_per_conv":1,
  "option":{"not_need_message":false,"need_complete_conversation":true,
            "need_coco_bot":true,"need_pc_pin_chain":true}}},
 "sequence_id":"<uuid>","channel":2,"version":"1"}
```
响应：`downlink_body.pull_recent_conv_chain_downlink_body.cells[]`，
每项 `.conversation.conversation_id` / `.conversation_status`
（注：实测 web cookie 下 cells 可能返回空，见「已知限制」）

### 2. 会话详情 POST /im/conversation/batch_get
```json
{"cmd":1111,"uplink_body":{"batch_get_conv_info_uplink_body":{
  "conversation_id":["<id1>","<id2>"],
  "option":{"recent_message_count_per_conv":3},"ext":{}}},
 "sequence_id":"<uuid>","channel":2,"version":"1"}
```

### 3. 发消息（SSE 流）POST /chat/completion
body 结构（抓包实测完整模板）：
```json
{
 "client_meta": {"local_conversation_id":"local_<13位>","conversation_id":"<会话id或空串新建>",
                  "bot_id":"7338286299411103781","last_section_id":"","last_message_index":null,
                  "local_permissions":[]},
 "messages": [{"local_message_id":"<uuid1>","content_block":[{"block_type":10000,
    "content":{"text_block":{"text":"<消息>","icon_url":"","icon_url_dark":"","summary":""},
    "pc_event_block":""},"block_id":"<uuid4>","parent_id":"","meta_info":[],
    "extra_info":{},"append_fields":[]}],"message_status":0}],
 "option": {"send_message_scene":"","create_time_ms":<ms>,"collect_id":"","is_audio":false,
    "answer_with_suggest":false,"agent_mode":2,"tts_switch":false,"need_deep_think":false,
    "...":"...按抓包模板原样保留"},
 "user_context": [],
 "ext": {"agent_mode":"2","use_deep_think":"0","sub_conv_firstmet_type":"1",
    "general_task_param":"{\"server_do_compare\":true}","collection_id":"","is_finish":"1",
    "...":"..."},
 "agent_mode": 2, "general_task_param": {...}, "is_ai_playground": false,
 "from_suggest": false, "answer_with_suggest": false, "click_clear_context": false,
 "edit_query_id": "", "disable_sse_cache": false, "append_sse_event_scene": "",
 "connector_info_list": [], "extra_info": {}
}
```
响应：SSE 流，`event: SSE_HEARTBEAT`（心跳）→ 正文事件 → 或 `STREAM_ERROR`

**实测经验**：
- 结构错误 → `710020202 common invalid param`
- 会话已死/风控 → `710020702 system error (is_replay:true)`
- 心跳正常但无正文 → 请求被受理，等待正文事件

### 4. 其他有用接口（同 header 即可调）
- POST /alice/user/config/pull — 用户配置
- POST /samantha/user/ab/get — AB 参数
- GET  /alice/profile/self — 个人信息（404 需带完整 query）
- POST /im/message/send_rate_limit — 发送限频检查

## 已知限制（2026-11-14 实测）

1. **web cookie 与会话归属**：扫码获得的 cookie uid 在 IM 接口可见，
   但若 cookie 过期（sid_guard 过期时间字段2），所有会话查询返回空、
   发送报 710020702。**判断 cookie 有效性看 send 是否报 710020702。**
2. `conversation_status` 字段可用于判断会话死活。
3. completion 的 option/ext 字段较多，建议用抓包模板整体替换文本字段，
   不要手写全量结构。

## v3 保活引擎设计（ka_http.py，待实现）

```
无浏览器！纯 HTTP：
├── login_check: account/info 或 recent_conv 判断 cookie 活性
├── list_convs:  recent_conv 拉会话
├── send:        chat/completion SSE 发送 + 错误码判定
│     ├ 710020202 → 参数错（代码 bug）
│     ├ 710020702 → cookie 死/会话死 → 触发扫码
│     └ 心跳+正文 → 成功
├── keepalive:   轮换任务发到目标会话（复用 v13 熔断/冷却逻辑）
└── tunnel_probe: 不变（检查 17800/18090）
```


---

## 五、短信登录接口（2026-11-14 实测）

### 1. 发送验证码 POST accounts.doubao.com/passport/web/send_code/

**手机号混淆算法（实测破解）**：
```
plain = "+86 " + 手机号          （注意 86 后有一个空格）
enc   = hex( bytes(plain).each_byte ^ 0x05 )
例：15888888888 → "+86 15888888888" → "2e3d332534303d3d3d3d3d3d3d3d3d"
验证：bytes("2e3d33...".hex_decode) ^ 0x05 == b"+86 15888888888"
```

**POST body（x-www-form-urlencoded）**：
```
mix_mode=1&mobile=<混淆hex>&type=3731&is6Digits=1&fixed_mix_mode=1
```

**URL query（关键参数）**：
```
passport_jssdk_version=4.4.6&passport_jssdk_type=normal&is_from_ttaccountsdk=1
&aid=497858&language=zh&ts=<unix秒>&p_ca=4.0.26&fp=<verify_fp>&verifyFp=<verify_fp>
&multi_login=1&account_sdk_source=web
```

响应成功后页面显示「验证码已发送至 +86 xxx」。

### 2. 提交验证码（待补全）
验证码输入框为 6 格 div 模拟，无法直接抓到 input 提交请求。
字节 passport 标准提交端点为 `/passport/web/msVerify/` 或 `/passport/web/login/`
（带 code/mobile 混淆参数）——待真实手机号触发后补录。

**当前登录方案**：
- 方案A（已打通）：扫码 → unified 页面
- 方案B（半打通）：send_code 已可真实发短信，提交接口待补
- 方案C（规划）：`/passport/web/auth/get_oauth_token/` 在未登录时也被调用，
  可能支持匿名换 token，待研究

### 3. 用户界面重做规划（v3 unified-lite）

```
18800 新页面（纯 HTTP，无浏览器）：
┌────────────────────────────────┐
│  登录区                        │
│  [手机号输入] [发送验证码]      │
│  [验证码输入] [登录]            │
│  ── 或 ──                      │
│  [显示二维码] (扫码兜底)        │
├────────────────────────────────┤
│  状态区: cookie活性/隧道/会话   │
│  保活控制: 启动/停止/目标会话   │
└────────────────────────────────┘
后端：unified_lite.py（Flask-free，http.server）
     登录代理 → passport 接口
     保活引擎 → ka_http.py
     旧 ka_v13/unified 浏览器版 → 废弃
```


---

## 六、chat/completion 的 a_bogus 障碍（2026-11-14 深夜结论）

### 现象
纯 HTTP 重放（结构完全一致、msToken 来自 cookie、device_id 等全参数复用）：
```
710020202 invalid param（is_replay:false）← 缺 a_bogus
710020702 system error（is_replay:true）  ← 旧 a_bogus 被判重放
```

### 已验证
- msToken 在 cookie 里（每 4 分钟轮换），query 里的必须与之配套
- `window.bdms.frontierSign(url, body)` 可生成 `{X-Bogus}` header，
  但 X-Bogus 是旧版 header 签名，服务端要的是 query 里的 `a_bogus`（新版）
- a_bogus 由豆包前端 JS 动态生成，绑定 URL+body+UA+时间戳，无法重放

### 结论
发送通道两条路：
1. **浏览器 UI 输入**（当前唯一验证可行）——豆包前端自动完成签名
2. 逆向 a_bogus 算法（字节系有开源实现，但豆包版本可能定制）

### 当前架构（混合）
```
unified（浏览器版，已修复超时+CPU问题）: 登录/发送（UI 通道）
ka_v13: 保活循环（调 unified /send）
ka_http: cookie 活性检查（纯 HTTP，每 30s）
unified_lite 页面: 独立管理台（备用，端口可切换）
```

### 已打通可复用的接口（纯 HTTP 无签名）
```
POST /im/chain/recent_conv       会话列表
POST /im/conversation/batch_get  会话详情
POST /passport/web/send_code/    短信验证码（XOR混淆手机号）
POST /passport/web/sms_login/    验证码登录（XOR混淆手机号+验证码）
GET  /passport/web/get_qrcode/   QR 拉取
GET  /passport/web/check_qrconnect/  QR 状态轮询
```


---

## 七、短信全自动登录打通（2026-11-15 08:26 实测成功）

### 完整流程（全部纯接口+浏览器UI混合）

```
1. 前置: 访问 doubao.com/chat 拿 base cookie
2. 前置: 访问 passport/web/login 拿 csrf
3. 发码: POST /passport/web/send_code/（手机号XOR 0x05混淆，type=3731）
4. 用户收码 → 提交: POST /passport/web/sms_login/（手机号+验证码都XOR混淆）
5. 收集响应全部 Set-Cookie（含 sessionid/sid_guard，TTL 6h-30d）
6. 活性验证: recent_conv 返回 status_code=0 + uid
```

**实测结果（08:26）**：
```
sid_guard 签发: 2026-11-15 08:26:42 | TTL 720h
sessionid + sessionid_ss 全拿到
活性: status_code=0 | uid=2328113677082323（主账号）
```

### 实现脚本
- `sms_auto.py`：全自动（登录+等码+提交+存cookie），轮询 `/root/sms_code.txt`
- `direct_sms.py`：纯HTTP发码
- `flow_sms.py`：带csrf前置的完整流
- `verify_deploy.py`：session 活性验证+部署

### 关键错误码对照
```
0     成功
7     访问太频繁（IP限频，等冷却或换浏览器流程）
1203  验证码过期/错误次数过多
1206  验证码发送太频繁
712012001 session 已过期
712012002 不支持编码类型（Content-Type 缺 encoding=utf-8）
710020202 completion 参数错误（缺/错 a_bogus）
710020702 completion 系统错误（is_replay=true → 签名被判重放）
710022002 completion 访问频繁
```

### chat/completion 签名难关（当前未破）
```
需要 query 参数 a_bogus（新版），浏览器内 bdms.frontierSign 只生成
旧版 X-Bogus header。GitHub 公开的 a_bogus Python 实现是抖音版本，
与豆包版本参数顺序/密钥有差异 → 签名被拒（invalid param）
```


---

## 八、710022002「访问频繁」的真相（2026-11-15 12:20 确认）

### 不是真的限频！
每次请求都是**固定 247 字节、立即返回**——真实限频不会这样。
这是服务端对该请求的**硬性拦截**。

### 根因分析
```
新账号（18053220144 注册的 uid=1008730618201603），
session 通过 API 有效（recent_conv 返回 status=0+uid），
但 samantha/chat/completion 报「访问频繁」。

原因候选：
1. 新账号需要先在网页完成首次设备验证/首次对话
2. 该账号缺少 device_id 绑定（sms_login 纯HTTP没有绑定浏览器设备）
3. 账号等级/风控评分过低
```

### 对照实验数据
```
空 cookie → recent_conv: 712012001 (过期)
假 cookie → recent_conv: 712012001
真 cookie → recent_conv: status=0 + uid=1008730618201603 ✓
真 cookie → samantha:   710022002 (无论 aid 是 497858 还是 582478)
```

### 可能的突破方向（未完成）
```
1. 从豆包页面 JS dump 完整的 a_bogus/frontierSign 算法
2. 在真实浏览器 UI 完成一次对话后，samantha 接口可能会解锁
3. 使用完整的 device_id 注册流程（不是 sms_login，而是完整客户端模拟）
```
