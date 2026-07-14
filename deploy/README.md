# Deploying diskosAI to homebase

homebase is a shared DigitalOcean Ubuntu box (Docker + systemd). The app runs as
one container, reads the DISKOS data from lambda-scalar over a read-only tailscale
SSHFS mount, and is fronted by your existing reverse proxy. Deploys happen on merge
to `main` via a self-hosted GitHub Actions runner on homebase.

```
GitHub (main)  --push-->  self-hosted runner on homebase
                              |  docker compose build && up -d
                              v
                          diskos-web  (127.0.0.1:8087)
                              |  reads /data (ro)
                              v
                    /srv/diskos/data  --sshfs/tailscale-->  lambda-scalar:/home/mnky9800n/data/DISKOS
```

## One-time setup on homebase

### 1. Mount the DISKOS data over tailscale (read-only sshfs)

```bash
sudo apt install -y sshfs
sudo mkdir -p /srv/diskos/data
echo user_allow_other | sudo tee -a /etc/fuse.conf      # let the container (root) read the FUSE mount
sudo ssh-keygen -f /root/.ssh/id_diskos -N ''
ssh-copy-id -i /root/.ssh/id_diskos.pub mnky9800n@lambda-scalar   # tailnet hostname (MagicDNS)

sudo cp deploy/srv-diskos-data.mount /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now srv-diskos-data.mount
ls /srv/diskos/data                                     # should list the DISKOS tree
```

Adjust `What=` in the unit if the user/host/path differ. The mount is read-only, so
the immutable source data is never at risk.

### 2. Production secrets

```bash
sudo mkdir -p /srv/diskos
sudo cp deploy/diskos.env.example /srv/diskos/diskos.env
sudo nano /srv/diskos/diskos.env        # allowlist, Google OAuth, session secret
sudo chmod 600 /srv/diskos/diskos.env
```

Google OAuth: create credentials at console.cloud.google.com, set the authorized
redirect URI to `https://<your-domain>/auth/callback`. Leave `DISKOS_WEB_DEV` unset
(the dev bypass must be off in production).

### 3. Self-hosted GitHub Actions runner

Settings -> Actions -> Runners -> New self-hosted runner (Linux x64) on the repo,
then on homebase follow the shown steps. Give it the label `homebase`:

```bash
./config.sh --url https://github.com/mnky9800n/diskos-explorer --token <TOKEN> --labels homebase
sudo ./svc.sh install && sudo ./svc.sh start
sudo usermod -aG docker $(whoami)       # runner user needs Docker; re-login after
```

### 4. Reverse proxy

Point a subdomain (e.g. `diskos.johnspace.xyz`) at `127.0.0.1:8087` in whatever
proxy already serves api.johnspace.xyz (nginx/caddy/traefik), with TLS. The
container only listens on localhost, so the proxy is the only public entry.

## Deploying

Merge a PR into `main`. The runner rebuilds and restarts the container. Verify:

```bash
curl -s localhost:8087/health
docker compose logs -f diskos-web
```

## Notes

- The container needs no DISKOS credentials: it reads the already-mounted `/data`.
- If lambda-scalar reboots, the sshfs mount reconnects (`reconnect` option); if it
  is down, data endpoints return an error until it is back.
- CI (`.github/workflows/ci.yml`) runs the test suite on every PR before merge.
