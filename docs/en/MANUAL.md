# DoubaoBox · Full User Manual (English)

> Turn your Doubao AI assistant into a free 24/7 server.

## What you need (4 items)

| # | Item | Notes |
|---|---|---|
| 1 | A machine with public IP | Your own VPS, 1 core / 512MB |
| 2 | A Doubao account | Your existing one |
| 3 | One QR scan | 30 seconds, first time only |
| 4 | (Optional) A domain | Only if you want a nice URL |

NOT needed: credit card, domain ICP filing, phone root, coding skills.

## Quick Steps

1. **Prepare relay machine** — open ports: 22, 80, 7000, 18800 (plus 17800, 18090 optional)
2. **Deploy relay** — `git clone https://github.com/Orengr/doubao.git && cd doubao && cp config.env.example config.env && nano config.env` (fill your IP) → `bash install.sh`
3. **Deploy sandbox** — open Doubao, new chat, switch to **Cloud Computer mode**, paste contents of `/root/SANDBOX_CMDS.txt`
4. **Scan QR** — open `http://YOUR_IP:18800/` → menu ≡ → Scan QR → scan with Doubao App
5. **Done** — visit `http://YOUR_IP/` for the dashboard, `/panel/` for 1Panel (admin / 123456)

## Troubleshooting

- Page down? → sandbox was recycled; send `sh /home/user/.dsh_pend/bin/ensure.sh` to Doubao
- Login expired? → re-scan QR at :18800
- Check all services: `bash bin/status.sh` on relay
- Run 88 self-tests: `bash test.sh`

## Limits

- Sandbox lifetime is controlled by ByteDance platform
- Session requires re-scan when expired (server-side design)
- For fully unattended hosting, consider real free containers (fly.io etc.)

## License

Non-commercial use only. See [LICENSE](../../LICENSE).
