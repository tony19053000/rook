# deploy/vendor/ (gitignored, except this file)

Put Bob Shell here for a live-mode image. It is **never committed** (its licence is unknown):

```bash
deploy/pack-bob.sh     # packs ~/.nvm/versions/node/v24.21.0/lib/node_modules/bobshell (2.0.5)
                       # -> deploy/vendor/bobshell-2.0.5.tgz (+ .sha256)
```

`deploy/Dockerfile` installs it to `/opt/bobshell` with a `/usr/local/bin/bob` wrapper that runs it on Node 24.
Without the tarball the image still builds and serves **replay mode only** (the build log and `start.sh` say so).
`deploy/aws/deploy.sh` copies this folder to the server with the rest of the repo.
