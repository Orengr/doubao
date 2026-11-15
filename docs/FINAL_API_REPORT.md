# 豆包接口逆向最终报告（2026-11-15，实测落库验证）

## 工具链
- REA 6.8.0（/tmp/rea）静态分析：FlowAccount SDK(chunk 324 atz)、WebInterfaceSdk(chunk ft)、加密模块 IOpb、签名引擎 bdms
- craft-anything CLI 0.6.1：web_walkthrough_record 抓包（登录态 535 req / 会话页 377 req）
- 决定性手段：**Xvfb 非 headless Chromium + CDP Network 录制 + 亲手点击发送按钮** —— 抓到消息真正发出那一刻的完整请求

## 登录（纯接口，已打通）
1. 页面环境 bdms.frontierSign 生成 X-Bogus
2. POST https://accounts.doubao.com/passport/web/send_code/ （mobile = "+86 18053220144" 逐字节 XOR 0x05）
3. POST https://accounts.doubao.com/passport/web/sms_login/ （mobile/code XOR 0x05 + login_only=false + fixed_mix_mode=1 + X-Bogus）
4. 响应含 user_id=2328113677082323 / name=小777 = 真登录
5. 立即导出全量 cookie（含 httpOnly）→ /root/ck_live2.txt

## 发送消息（真正落库的接口）
**POST https://www.doubao.com/chat/completion?<params>**（不是 /samantha/...，不是 /alice/message/stream_call_bot）

- Headers: Content-Type: application/json / Agw-Js-Conv: str, str / Referer: https://www.doubao.com/chat/<conv_id>
- URL params: aid=497858, device_id=7707456447802197504, web_id=7708309532624045619, tea_uuid=同web_id,
  fp=verify_mwhkbev6_...(来自 cookie s_v_web_id), msToken, web_tab_id(每请求新 UUID),
  pc_version=3.45.7, version_code=20800, region=CN, tz_name=Asia/Shanghai,
  samantha_web=1, use-olympus-account=1, web_platform=browser, **a_bogus=...**（bdms 底层注入）
- Body: client_meta{conversation_id, bot_id=7338286299411103781, last_section_id, last_message_index}
  + messages[].content_block[].content.text_block.text（嵌套块，不是 content 字符串）
  + 巨型 option（agent_mode=1, need_deep_think=9, unique_key/local_message_id 每请求新 UUID ...）
- 成功标志: SSE_ACK 事件含 query_list[].question_id + message_index；会话记录可查到

## 之前全错在哪
| 错误 | 后果 |
|---|---|
| 用 /samantha/chat/completion | 710022002/710022004 风控 |
| 用 /alice/message/stream_call_bot | conversation_id="0" 无状态通道，回复是回显，不落库 |
| body 用 messages[].content 字符串 | 结构不对 |
| 手搓 a_bogus/X-Bogus 短签名 | 真签名是 bdms 底层注入的长串 |
| cookie 与其它设备 ID 混用 | Invalid User ID / 风控验证（xdpool 思路修正）|

## 读取接口（已验证）
- POST /im/chain/recent_conv（cmd 3200）会话列表
- POST /im/conversation/info（cmd 1110）会话详情
- POST /im/chain/single（cmd 3100）消息记录 ← 唯一验收标准
- POST /im/message/send_rate_limit（cmd 2260）
- Content-Type: application/json; encoding=utf-8（豆包专用，不是 charset）

## xdpool 借鉴（凭证存储）
credential 对象把 accessToken/refreshToken/uid/domain 绑成整体存 accounts.json（原子 rename）；
deriveDeviceId = sha256(salt + uid) 派生稳定设备 ID，每账号固定一台设备，跨重启不变。
本项目落地：doubao_account_device_profile.json —— cookie + device_id/web_id/fp/msToken/UA 绑成一份档案。

## 可运行组件
- /root/doubao_send.py <conv_id> <text> —— 经真浏览器页面环境发 /chat/completion，实测落库
- /root/ka_pure.py —— 已改为调用 doubao_send.py，目标会话 38453425674259202
- /root/ck_live2.txt —— 真登录全量 cookie
- 前置：Xvfb :99 + 非 headless chromium CDP 9222 + 档案内 cookie 已注入

## 铁律
- cookie 有效期内绝不重新登录（单点会话，一次登录顶掉全部）
- 验收只认 /im/chain/single 里查得到的消息
- 绝不使用无状态通道的回复当"发送成功"
