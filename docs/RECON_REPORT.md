# 豆包接口逆向侦察报告（REA + craft-anything）
> 2026-11-15 13:55 · 会话：Little Code Sauce

## 工具链（已就绪）
- REA 6.8.0: /tmp/rea，source /opt/rea-tools/env.sh + node strip-types 启动（见 REA-STARTUP.md）
- craft-anything CLI 0.6.1: /tmp/craft-sq/usr/bin/craft-anything-cli（AppImage 官方 SHA256 校验通过，--deep 已开）
- 本机 Chromium SIGILL（CPU 无 LSE），改用服务器 headless Chromium 157 + CDP 9222 + SSH 隧道 -L 9222
- 抓包通道: craft-anything-cli web-walkthrough-record --actions '[...]' --cdp-endpoint http://127.0.0.1:9222 --keep-bodies '{"request_body":true,"response_body":true,"header_values":true}' --capture-network true
- 抓包数据: /tmp/wt-run1.json（未登录 437 req）、/tmp/wt-auth.json（登录态 535 req）、/tmp/wt-session.json（377 req）、/tmp/wt-target2.json（目标会话页 377 req）

## 新破接口（curl 纯接口复放验证 ✅，无需签名）
| 接口 | cmd | 状态 | 说明 |
|---|---|---|---|
| POST /im/chain/recent_conv | 3200 | ✅ 复放成功 | 会话列表+置顶分页，direction 3/1，conv_version 游标翻页 |
| POST /im/conversation/info | 1110 | ✅ 复放成功 | 会话详情（creator_id/name/icon），live conv 返回 OK |
| POST /im/chain/single | 3100 | ✅ 接口通(cmd 0) | 消息记录；conversation_id 必须有效，否则 712017001 数据不存在 |
| POST /im/message/send_rate_limit | 2260 | 已抓包 | 发送限频预检 |
| samantha/chat/completion | - | 710022002 限频中 | 上会话已打通（test_sam4.py），当前账号风控 |

## 关键修正
1. Content-Type 必须是 `application/json; encoding=utf-8`（不是 charset！）→ 解决 712012002
2. 请求头 agw-js-conv: str + accept: application/json, text/plain, */*
3. device_id 用 7707456447802197504、region=CN、samantha_web=1、use-olympus-account=1

## 会话现状
- 旧目标会话 38453425674259202 已被豆包删除（712017001），URL 也 404 语义
- 当前唯一活跃会话: 38453557429729794（ka_pure 置顶，creator=1008730618201603）
- 登录态有效: uid 1008730618201603（get_web_anon_id 确认）

## 风控现状（待处理）
- ka_pure 每 3 分钟发重复恢复指令 → 13:39 起豆包停止回复（回复空），test_sam4.py 确认 710022002
- 建议：降低频率（≥10min）+ 消息内容加随机时间戳变化 + 等限频冷却

## 下一步
1. 等 710022002 冷却（通常 1-24h），期间不动发送
2. 用会话切换接口抓包（craft walkthrough 点击侧栏会话）补齐「切换会话」接口
3. 云电脑切换接口：walkthrough 操作豆包云电脑入口
4. 消息记录为空问题：发一条新消息后重拉 single 确认消息落库字段
