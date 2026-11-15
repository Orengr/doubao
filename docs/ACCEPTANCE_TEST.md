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
