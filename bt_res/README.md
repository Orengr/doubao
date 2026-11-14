# 离线资源目录（可选）

把预下载好的压缩包放这里，部署时**优先用本地文件**，不再从公网下载。

```
bt_res/
├── frp.tar.gz        frp 0.72.0 linux-amd64（约 14MB）
└── 1panel.tar.gz     1Panel v1.10.34-lts linux-amd64（约 47MB）
```

## 两种用法

### A. 直接放进仓库（推荐给开源分发）
把这两个文件提交到 Git，用户 `git clone` 后就有全部资源，
部署时零公网下载、不吃豆包额度。

> 仓库会变大（约 61MB），但 GitHub 单仓库上限 1GB，完全没问题。
> 原项目 `Orengr/doubao-bt-deploy` 也是这么做的（bt_res/ 下放了 68MB）。

### B. 不提交，让中转机首次部署时自动下载
install.sh 会自动从公网下载一次到 `bt_res/`，之后复用。
沙箱始终从中转机内网拉取，不吃额度。

## 下载命令（自己备好资源时）

```bash
cd bt_res
curl -fsSL -o frp.tar.gz \
  "https://ghfast.top/https://github.com/fatedier/frp/releases/download/v0.72.0/frp_0.72.0_linux_amd64.tar.gz"
curl -fsSL -o 1panel.tar.gz \
  "https://resource.fit2cloud.com/1panel/package/stable/v1.10.34-lts/release/1panel-v1.10.34-lts-linux-amd64.tar.gz"
```

## ⚠️ 提交前检查
这两个是公开二进制，**不含任何账号/密钥**，可放心提交。
不要把你自己的 `frps.toml`、`ck_full.txt`、`keepconf.json` 放进这个目录。
