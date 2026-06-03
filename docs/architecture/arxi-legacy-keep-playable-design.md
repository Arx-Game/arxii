# Arx I — Legacy Keep-Playable (Frozen Container Relocation)

- **Date:** 2026-05-16
- **Status:** Draft (design approved in brainstorm; pending spec review + user review)
- **Sub-project:** #2 of 2. **Hard dependency:** requires `2026-05-16-arxii-observability-baseline-design.md` (sub-project #1) to exist first.

## 1. Context & Motivation

Arx I (the predecessor game, still narratively run by the user's brother) is **still live** on an old Linode: ancient, badly out-of-date Ubuntu, sqlite database, ~$40/mo. The team wants Arx I to **remain playable short-term**, cost-bounded, with the option to decommission later if the resource cost is not worth it.

Key constraints established in design:
- **Data is not critical.** Backups exist (possibly stale); total loss "wouldn't be a complete disaster." This is a normal legacy-relocation job, **not** a drop-everything security emergency. Tone/urgency calibrated accordingly.
- The insecurity is primarily at the **host/OS** layer (unpatched kernel, ancient OpenSSH/TLS, dead system libraries), not necessarily fatal at the app layer.

## 2. Goal & Non-Goals

### Goal
Relocate Arx I, unchanged, onto modern reproducible infrastructure as a **frozen, isolated container**, and retire the insecure $40/mo box as a side effect.

### Non-goals
- **Not** patching or modernizing the Arx I application.
- **Not** an ETL of Arx I data into Arx II's schema (explicitly rejected).
- **Not** an emergency — no rushed decisions; the relocation *is* the preservation.

## 3. Hard Dependency & Sequencing

Depends entirely on sub-project #1 being built first: the modern patched host, OpenTofu/Ansible codebase, and Caddy that the legacy container co-resides on and sits behind. Sequence: **build #1 → then this spec drops the frozen container onto that host and retires the old box.**

## 4. Architecture

**Freeze the app; modernize the host.** The ancient stack runs unchanged inside a container that pins its exact Python/Evennia/Django/sqlite versions. The host is the modern, patched sub-project-#1 box. Caddy on that host reverse-proxies to the legacy container, giving Arx I **modern TLS termination without touching its ancient TLS stack**.

### 4.1 Capture (critical detail)
Pull the **entire virtualenv / site-packages directory** off the old box, not just code + sqlite. Ancient pinned dependencies are often no longer installable from PyPI (yanked, or won't build against modern libs); the existing installed `site-packages` is the only reliable image input. This same complete copy *is* the preservation snapshot — migration and backup are the same artifact; there is no separate "preserve it" task.

### 4.2 Placement & isolation (co-resident — hardening is load-bearing)
The container runs **co-resident on the Arx II prod box** (cost-first decision: kills the $40 box at zero marginal cost). Because a known-insecure app shares a host with Arx II + its Postgres, container hardening is **mandatory, not optional**:

- Unprivileged container, read-only root filesystem except the sqlite/game data volume.
- Dropped Linux capabilities.
- Strict cgroup memory/CPU caps — a leaky or compromised ancient app must not OOM or starve the host running Arx II + Postgres (same DB-corruption-via-side-door failure mode that `MemoryMax` guards in sub-project #1).
- **Network isolation:** separate container network, no shared volumes; Arx II's Postgres bound to localhost/unix-socket and unreachable from the legacy container.

### 4.3 Honest accepted risk
Containerization isolates blast radius and caps damage; it does **not** patch Arx I's own application-level CVEs. Given short-term horizon + low data criticality, "isolated but not internally patched" is an accepted, informed tradeoff — a decision, not an accident.

## 5. DNS Cutover (executed during relocation)

Arx I's domain/registrar stays as-is until this relocation runs. At cutover:

1. **Identify reality, don't trust memory:** `whois <domain>` (registrar — almost certainly Squarespace, ex-Google Domains) and `dig NS <domain>` (current authoritative nameservers).
2. **Inventory every record authoritatively** via `dig` (A/AAAA, CNAME, NS, and especially **MX + SPF/DKIM/DMARC TXT**). Email is the silent killer: moving nameservers without faithfully recreating mail records breaks email with no error.
3. **Rebuild the full zone in Linode DNS as code** (OpenTofu), initially pointing at the old box (delegation-only, content-neutral).
4. **Validate before flipping:** query Linode's nameservers directly (`dig @ns1.linode.com …`) and confirm correct answers.
5. **Flip nameservers at the registrar** to Linode's. (Registrar transfer is **not** required — only nameserver delegation.)
6. **Repoint the A record to the new host separately,** after delegation is stable (two-phase: delegate-then-repoint).
7. Caddy auto-ACME succeeds once DNS resolves to the new box.

## 6. Off-Ramp & Split-Out (designed in)

- **Decommission later (off-ramp to cold archive):** because it is container + data volume, "shut down if cost isn't worth it" = snapshot the data volume to the archive bucket + `tofu destroy`. Choosing keep-playable does not lock in; it degrades cleanly to cold-archive with no second migration project.
- **Split to its own node (escape hatch):** because it is container + data volume + Terraform-managed, splitting out if co-residence proves problematic = `tofu apply` a tiny separate node, move container + volume, repoint Caddy. Pre-designed; carries no redesign cost.

## 7. Failure Modes & Handling

| Failure | Handling |
|---|---|
| Ancient deps un-resolvable from PyPI | Image built from captured `site-packages`, not re-resolved |
| Legacy app compromised | Network isolation + dropped caps + cgroup caps contain blast radius; cannot reach Arx II Postgres |
| Legacy app leaks memory | cgroup cap bounces the legacy container only; Arx II + Postgres unaffected |
| Email breaks on DNS move | MX/SPF/DKIM/DMARC inventoried and recreated; validated against Linode NS before flip |
| Co-residence becomes a problem | Pre-designed split-out to its own node |
| Cost not worth it later | Pre-designed off-ramp to cold archive |

## 8. Acceptance Criteria

1. The captured Arx I artifact (code + sqlite + full `site-packages` + config) is verified complete and restorable.
2. The frozen container runs Arx I unchanged on the sub-project-#1 host, reachable over modern TLS via Caddy.
3. Hardening verified: container is unprivileged, capped, and provably **cannot** reach Arx II's Postgres.
4. DNS cutover completes with **email still working** (MX/TXT validated) and no registrar transfer.
5. The insecure $40/mo box is powered down and destroyed after cutover verification.
6. Off-ramp and split-out procedures are documented and dry-run-validated as `tofu`/Ansible operations.

## 9. Honest Risks & Accepted Tradeoffs

- **Isolated, not internally patched** — accepted given short-term + low data criticality.
- **Co-residence with prod Arx II** — accepted for cost; mitigated by mandatory hardening + pre-designed split-out.
- **Stale backups** — accepted; the relocation captures a fresh complete copy, and migration mechanics (not data currency) are what matter for keep-playable.
