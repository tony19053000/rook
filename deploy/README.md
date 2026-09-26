# deploy/: the hosted Rook server on AWS EC2

One EC2 host runs two containers with Docker Compose: **Caddy** (HTTPS on 80/443 with a Let's Encrypt certificate
for `<ip-dashes>.sslip.io`) and **rook** (the FastAPI server, reachable only through Caddy). The web app on Vercel
proxies `/api/v1/*` to it. Design and settings: `docs/02_ARCHITECTURE.md` §14; security: `docs/03_SECURITY_ACCESS.md`.

| File | What |
|---|---|
| `Dockerfile`, `start.sh` | the server image (build from the repo root) and its entry point |
| `docker-compose.yml`, `Caddyfile` | rook + Caddy |
| `demos/` | the sandbox allowlist, the demo catalog, and the pinned demo repos (`repos.txt`, `build-demos.sh`) |
| `pack-bob.sh`, `vendor/` | the optional Bob Shell for live mode (gitignored, never committed) |
| `smoke.py` | checks a running server like a guest would (health, repos, one replay demo run) |
| `aws/` | `create.sh`, `deploy.sh`, `destroy.sh`, `ssh.sh`, `scripts/set-secret.sh` (+ `remote/set_env.py`, `user-data.sh`) |

All AWS calls use `uvx --from awscli aws --profile rook --region us-west-2`.

## Run it (in this order)

```bash
# 0. once: an AWS CLI profile named "rook" (an IAM user with EC2 rights)
uvx --from awscli aws configure --profile rook

# 1. optional, for live Bob: pack the local Bob Shell 2.0.5 into deploy/vendor/ (gitignored)
deploy/pack-bob.sh

# 2. create the host (shows the plan, asks y/N; idempotent, rerun safely)
deploy/aws/create.sh

# 3. copy the repo, build, start, wait for https://<ip-dashes>.sslip.io/api/v1/health
deploy/aws/deploy.sh
#    later, once the Vercel URL is known (CORS for direct calls):
#    ROOK_WEB_ORIGINS=https://<project>.vercel.app deploy/aws/deploy.sh

# 4. secrets (each one prompts with hidden input and restarts rook)
deploy/aws/scripts/set-secret.sh ROOK_GUEST_SECRET   # optional: deploy.sh already made one on the host
deploy/aws/scripts/set-secret.sh BOB_API_KEY         # only needed for live mode
#    later (ROOK-030/031): SUPABASE_URL, SUPABASE_JWT_SECRET, GITHUB_APP_ID, GITHUB_WEBHOOK_SECRET and
deploy/aws/scripts/set-secret.sh GITHUB_APP_PRIVATE_KEY < path/to/app.pem

# 5. verify: a guest replay demo run through Caddy (0 Bobcoins)
uv run python deploy/smoke.py https://<ip-dashes>.sslip.io

# live Bob (after steps 1 and BOB_API_KEY): redeploy in live mode, with the daily coin cap
ROOK_BOB_MODE=live ROOK_DAILY_COIN_CAP=2 deploy/aws/deploy.sh
```

Other commands: `deploy/aws/ssh.sh` (a shell), `deploy/aws/ssh.sh 'cd rook/deploy && sudo docker compose logs --tail 100'`,
`deploy/aws/destroy.sh` (deletes everything, asks first).

## Notes

- **SSH** is open only to the IP you ran `create.sh` from. If your IP changes, rerun `create.sh`: it adds the new /32
  (old rules stay until you remove them in the console or with `destroy.sh`).
- **Secrets** live only in `/etc/rook/rook.env` on the host (root, 600). `set-secret.sh` sends the value over ssh
  stdin; it never appears in argv, shell history or logs. Non-secret settings are in `rook/deploy/.env` on the host,
  written by `deploy.sh`.
- **No keep-alive**: EC2 does not sleep. For monitoring, point any uptime checker at `/api/v1/health` (it is exempt
  from the rate limit).
- **Local test** of the same stack over plain HTTP:
  ```bash
  docker build -f deploy/Dockerfile -t rook-server:local .
  printf "ROOK_GUEST_SECRET='%s'\n" "$(openssl rand -hex 32)" > /tmp/rook.env
  cd deploy && ROOK_ENV_FILE=/tmp/rook.env ROOK_HOST=http://localhost ROOK_HTTP_PORT=18080 ROOK_HTTPS_PORT=18443 \
      docker compose -p rooktest up -d
  uv run python deploy/smoke.py http://localhost:18080
  docker compose -p rooktest down -v
  ```
- **Demo apps (ROOK-039)**: add each repo to `demos/repos.txt` (pinned SHA), `demos/allowlist.yaml` and
  `demos/demos.yaml`, plus its Bob recordings to the image, then `deploy.sh`.
- Costs: about 0.02 USD/hour for the `t3.small` (standard CPU credits), 0.005 USD/hour for the public IPv4, plus
  30 GB of gp3. Run `destroy.sh` after judging.
