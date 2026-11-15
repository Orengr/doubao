# 快速开始（3 分钟）

## 给豆包一句话

> 请读取 https://raw.githubusercontent.com/Orengr/doubao/main/AUTODEPLOY.md 并按它执行全自动部署

## 手动部署（自己动手）

### 沙箱侧

```bash
cd /home/user/.dsh_pend
git clone --depth 1 https://github.com/Orengr/doubao.git moin-deploy
cd moin-deploy

# 预编译包放到 pkg/（见 Releases）
mkdir -p /home/user/.dsh_pend/pkg

# 一键安装（后台跑，避免中断）
setsid nohup sh install_all.sh > /tmp/install.log 2>&1 < /dev/null &
sleep 120 && tail -30 /tmp/install.log
```

### 中转机侧

```bash
git clone --depth 1 https://github.com/Orengr/doubao.git /root/moin
echo "<沙箱token>" > /root/sbx_token.txt
systemctl enable --now moin-unified sbx-guard ka-pure tunnel-watch
```

## 访问

| 入口 | 地址 |
|---|---|
| 面板 | `http://<IP>/panel` |
| 管理台 | `http://<IP>/lite/` |
| 导航页 | `http://<IP>/` |

## 沙箱重置后

```bash
sh /home/user/.dsh_pend/bin/start_all.sh
```

## 下一步

- 看面板 → 网站 → 新建网站
- 或看 `docs/MANUAL.md` 详细手册
