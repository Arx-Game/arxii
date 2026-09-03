# Gated devcontainer → prod SSH access (agent ops)

Lets the operator grant a devcontainer session SSH access to the prod Linode
for a specific piece of server work, and revoke it just as deliberately. Both
sides fail closed: a container brought up without the toggle has no key AND
no network route; a server converged without the pubkey Variable accepts no
login for the ops user.

Threat model: an agent inside the devcontainer doing something catastrophic
on prod without the operator having consciously opened the gate. It does NOT
defend against host-machine compromise (the key lives on the host), and it
does not protect the backups from a compromised box — that backstop is
bucket-side immutability (R2 Object Lock, tracked in #2236 / infra README
"Known gap: Object Lock").

## The pieces

| Layer | Where | Toggle |
| --- | --- | --- |
| Key possession | devcontainer mount → `~/.ssh/arxii_ops` | `ARXII_OPS_KEY_DIR` env var at `just dc-up` time |
| Network egress | container firewall REJECT of prod:22 | same mount (key absent = blocked) |
| Server account | `arxops` user, key-only, scoped sudo | `ARXII_OPS_SSH_PUBKEY` gated Environment **Variable** |

The server user `arxops` (roles/ops_access) is least-privilege by design:
`journalctl` and `/var/log` reads via groups, sudo for exactly
`systemctl reload/restart/start arxii`, and nothing else — no Postgres, no
`/etc/arxii` secrets, no user management. Real surgery stays on `arxadmin`,
performed by a human.

## One-time setup (operator)

1. **Mint the keypair** on your host machine (NOT inside the devcontainer,
   NOT inside the repo):

   ```bash
   mkdir -p ~/arxii-ops-key
   ssh-keygen -t ed25519 -f ~/arxii-ops-key/arxii_ops -C arxii-ops-devcontainer -N ""
   ```

   The comment matters: it's what you'll grep for in the box's
   `/var/log/auth.log` to tell agent sessions from your own. Keep the
   directory OUTSIDE the repo checkout — the repo dir is bind-mounted into
   the container wholesale, which would defeat the gate (and `git clean
   -fdx` must never be able to eat a private key).

2. **Authorize it server-side**: set the gated `prod` Environment
   **Variable** (not secret — it's a public key) `ARXII_OPS_SSH_PUBKEY` to
   the single-line content of `~/arxii-ops-key/arxii_ops.pub`, then press
   the button ("Stand up infra"). The converge creates `arxops` and installs
   the key.

3. **Rebuild the devcontainer image once** after this feature lands
   (`just dc-build`) — the firewall script is baked at image build time.

## Opening the gate for a session

```bash
just dc-down
ARXII_OPS_KEY_DIR=$HOME/arxii-ops-key just dc-up
```

(From a Windows shell, use the path form your Docker accepts, e.g.
`C:\Users\you\arxii-ops-key`.) On start, the firewall log line says
`Prod ops gate: OPEN`, the key is copied to `~/.ssh/arxii_ops` with 0600
perms, and `ssh arxii-prod` works (host alias written to `~/.ssh/config`;
first contact pins the host key via `accept-new`).

## Closing the gate

```bash
just dc-down && just dc-up   # without the env var
```

The mount reverts to the committed empty `no-ops-key/` dir: the firewall
REJECTs prod:22 again and the container-side key copy is deleted at start.
For a stronger revoke (e.g. you suspect the key leaked), also clear the
`ARXII_OPS_SSH_PUBKEY` Variable and press the button — the server then has
an empty `authorized_keys` and the key is dead everywhere; re-mint a fresh
pair before the next session.

## Verifying the gate state

Inside the container: `ssh -o BatchMode=yes -o ConnectTimeout=5 arxii-prod true`
— exits 0 when open; "Connection refused"/"No route to host" when closed.
The postStart output also prints the gate state on every container start.

## Reading the game logs

Since #3599 the game writes its log files to `/var/log/arxii` on the box
(`LOG_DIR` in the EnvironmentFile; `roles/app_deploy` creates the directory
as `arxii:adm` 0750 and a systemd-tmpfiles rule deletes files older than 30
days). `arxops` is in `adm`, so with the gate open it reads them with no sudo:

```bash
ssh arxii-prod tail -n 200 /var/log/arxii/server.log
ssh arxii-prod grep -n 'AccountDB' /var/log/arxii/server.log
ssh arxii-prod ls -la /var/log/arxii            # rotated copies: server.log.YYYY_MM_DD
ssh arxii-prod journalctl -u arxii --since '1 hour ago' --no-pager
```

`server.log` is the game process (Evennia's own lines plus, since #3599,
Django's `logging` output, which used to be discarded in daemon mode);
`portal.log` is the network process; `http_requests.log` is one line per
web request, including client IPs. Every error-level line in `server.log`
is also a Sentry event (tag `logger: evennia.twisted`), so check Sentry
before opening the gate for a traceback.

A production traceback never goes into a public issue or PR
([ADR-0254](../adr/0254-sentry-digest-is-a-pointer-not-a-reproduction.md)).
