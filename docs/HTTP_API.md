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
