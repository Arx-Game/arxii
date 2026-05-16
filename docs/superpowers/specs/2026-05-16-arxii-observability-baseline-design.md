# Arx II — Sane Single-Host Baseline + Observability + IaC Deploy

- **Date:** 2026-05-16
- **Status:** Draft (design approved in brainstorm; pending spec review + user review)
- **Sub-project:** #1 of 2 (foundation). Prerequisite for `2026-05-16-arxi-legacy-keep-playable-design.md`.

## 1. Context & Motivation

Arx II is a web-first, mobile-friendly narrative roleplaying platform built on Evennia, consumed as a pinned git dependency. **No Evennia source changes have been made, and whether Arx II ever needs to fork Evennia is an open question** — initial research suggests not in the near term. The realistic concurrent-player scale is **genuinely unknown** — the predecessor (Arx I) peaked ~300 with zero advertising, and the team must be prepared for substantially more.

Through design analysis we established:

- Evennia's real scaling ceiling is **single-reactor-thread CPU + the in-memory idmapper**, not the Portal/network layer. A Rust portal/bridge rewrite addresses none of the top constraints.
- The compute taxonomy (scene-local reactive vs. global periodic scripts/tickers vs. per-connection I/O) and the flows-vs-scripts cost ratio are **unmeasured**. Every scaling decision (hardening, scene-sharding, gateway) is currently a guess.
- Arx I's production scars were operational, not architectural: sqlite corruption + lock storms, no observability, hand-configured nginx, `screen`, no reproducible deploy.

**Therefore this sub-project deliberately builds no scaling architecture.** It builds the operational floor and the *measurement* that makes every later architectural decision evidence-based instead of guessed. It is strictly better than the Arx I stack for comparable cost.

## 2. Scope

### In scope
A reproducible single-host production environment with: Postgres, supervised processes, automated TLS, infrastructure-as-code provisioning, tag-driven CI/CD deploy, ephemeral staging, and an in-process observability layer.

### Explicit non-goals (deferred behind the metrics this produces)
- No Arx II boundary hardening (Actions/Flows off `ObjectDB`/`msg()`).
- No scene-sharding, no stateless gateway, no Rust components.
- **Zero Evennia-core changes.** Evennia is consumed as an unmodified, pinned upstream dependency; no fork (carrying patches) exists today and this sub-project introduces none. Whether scaling work *ever* requires Evennia-core changes is explicitly deferred behind the metrics this produces. The observability exporter is Arx II code that *reads* Evennia internals; it does not modify them.

## 3. Architecture Overview

A single Linode VPS (Arx I cost parity, ~$40/mo class) hosting, co-resident: the Arx II game process, Postgres, Prometheus, Grafana. Provisioned and deployed by **one OpenTofu + Ansible codebase** in the `arxii` monorepo (`infra/`). Releases are tag-triggered through GitHub Actions, gated, and applied via `evennia reload` where possible. A short-lived stage box is spun from a backup for pre-promotion sanity checks and destroyed after.

```
Internet
  -> Caddy (auto-ACME TLS, reverse proxy)
       -> Evennia/Arx II game process (systemd, MemoryMax)
       -> Django site / REST / SPA (off the realtime path)
  Postgres (own cgroup, reserved memory)        | same box
  Prometheus + Grafana + node_exporter          |
  off-box heartbeat  ->  external alert (free tier)
OpenTofu (Linode: instance, volume, firewall, DNS, bucket; state in bucket)
  -> Ansible provision (incl. restore-from-backup role)
  -> Ansible deploy (release dir + `current` symlink)
GitHub Actions: tag -> build/test artifact -> approval gate -> playbook -> health gate
```

## 4. Components

### 4.1 Storage & process baseline
- **Postgres replaces sqlite.** Retires the corruption + write-lock-storm outage class (whole-db lock → MVCC + row locks; no mid-write file corruption). It does **not** address the single-reactor compute ceiling — a separate axis, deliberately out of scope. Removing sqlite write-lock stalls also makes observability data interpretable (one fewer confound).
- **systemd units** (not `screen`): auto-restart, `journalctl`, boot persistence. `MemoryMax=` on the game unit so a runaway/leak gets cgroup-killed and restarted **instead of OOM-killing the box** (which would take Postgres with it and recreate the Arx I corruption scar by a side door). Postgres runs in its own cgroup with reserved memory and is not co-killable by the game service.
- **Backups:** nightly `pg_dump` to Linode Object Storage.

### 4.2 Observability (the actual point of this sub-project)
In-process exporter exposing Prometheus metrics on `/metrics`. Lives in Arx II source (`src/…`); it *reads* Evennia internals but does not modify Evennia-core.

- **idmapper cache gauge:** walk every `SharedMemoryModel` subclass; report `len(__instance_cache__)` and a `pympler.asizeof` byte estimate per model. Converts the unbounded-memory fear into a graphed slope + threshold.
- **Reactor-loop lag:** a fixed-interval `LoopingCall` measuring scheduled-vs-actual delta. The single most important "is the one process keeping up" signal; directly measures head-of-line blocking.
- **Per-subsystem timing histograms:** wrap command (`cmdhandler`), flow (`emit_event`/`FlowStack`), and script/ticker callback dispatch, keyed by subsystem and name. This is what **empirically settles flows-vs-scripts** rather than guessing.
- **GC pause time** via `gc.callbacks` (large cyclic graphs make GC expensive; avoids misattributing GC stalls to game logic).
- **Surfacing:** Prometheus + Grafana + node_exporter co-resident; a free off-box heartbeat (e.g. healthchecks.io) pinging the health endpoint so an alert still fires when on-box monitoring dies with the box; `py-spy` installed for on-demand live attach; an in-game admin command dumping the same numbers (introspect prod with no shell).

### 4.3 Infrastructure-as-code (OpenTofu)
- OpenTofu (license-clean Terraform fork), Linode official provider: `linode_instance`, `linode_volume`, `linode_firewall`, `linode_domain`/`_record` (Arx II's own new domain), `linode_object_storage_bucket`.
- **State** in the same Linode Object Storage bucket family as backups (S3 backend, native lockfile). Losing local state is the classic solo-operator footgun; externalizing it is the cheap correct fix. Repo never contains state or secrets.
- **Separation rule:** Terraform provisions resources only. Data restore is **not** modeled in Terraform state — it is an Ansible role that *uses* the provisioned target.

### 4.4 Configuration management + deploy (Ansible)
- One Ansible codebase performs **both provisioning and deploy**. The playbook is the version-controlled, executable definition of "what an Arx II box is and how a release reaches it."
- Deploy uses the **release-directory + `current` symlink** pattern: each release in `releases/<tag>/`, atomic symlink repoint, instant code-rollback by repointing to the previous release.
- **Restore-from-backup role** is pluggable: nightly `pg_dump` now; WAL archiving (pgBackRest/WAL-G to the same bucket → minutes-RPO point-in-time recovery) is a deferred lever, a config change not a redesign.
- **Reload-not-restart:** code-only releases apply via `evennia reload` (the Portal keeps players connected — Evennia's two-process model). Hard restart only for dependency, Portal, or settings changes.

### 4.5 CI/CD (GitHub Actions)
- Trigger **only** on a semver release tag. GitHub Actions tag filter (glob) `v[0-9]*.[0-9]*.[0-9]*-release`; CI's first step then strict-regex-validates the tag against `^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)-release$` and hard-fails before doing anything if malformed. Net: only a deliberate, semver-shaped `vMAJOR.MINOR.PATCH-release` (e.g. `v1.2.3-release`) deploys — `very-cool-tag`, a bare `v1.2.3`, and a non-semver `v1.2-release` all trigger nothing. Build + test, publish a reproducible artifact (deps resolved in CI, not on the box at deploy time).
- **Approval gate:** a GitHub Environments "approve" button (not SSH) before prod.
- CI invokes the Ansible playbook; it does not contain the deploy logic. Deploy logic is runnable independent of GitHub.
- **Post-reload health gate:** reads §4.2 metrics (reactor lag, error rate); failure → automatic code-rollback (symlink to previous release).
- **Migration safety gates (load-bearing because single-box / no staging).** Explicitly **not** a reversibility check: Django schema migrations are reversible by default, and an intentionally-irreversible data migration (`RunPython` with no reverse, by design) is legitimate and must **never** be flagged. Reversibility is the wrong property — the binding constraint is that after migrating, the **previous code release must still run against the new schema**, because auto-rollback reverts *code, never schema*, and `evennia reload` briefly overlaps old and new code. Two complementary checks plus an optional escalation:
  1. **Expand/contract classifier (forces an explicit decision; does not pretend to auto-judge).** CI parses the migration's operations and flags the runtime-incompatible classes: `RemoveField`, `DeleteModel`, `RenameField`/`RenameModel`, `AlterField` that narrows type or adds `NOT NULL` without a default, and opaque `RunSQL`/`RunPython`. A flagged migration **fails CI unless it carries an explicit marker** (e.g. `# release-safety: expand` or `# release-safety: contract — old code gone since vX.Y.Z`) acknowledging which expand/contract phase it is. Rationale: "is this backward-compatible?" is undecidable in general (`RunSQL`/`RunPython` are opaque), so the gate's job is to force the expand/contract decision to be *declared and reviewed*, not to compute a verdict it can't.
  2. **Apply-against-real-data dry-run.** The migration runs against a fresh restore of the prod DB *before* the live DB is touched — catches execution failures (e.g. `NOT NULL` on existing rows, a bad `RunPython`) that only surface on real data. Complementary to (1): proves it *applies*, not that old code survives it.
  - *Recommended escalation (named, optional — deferred by default for cost/solo):* a CI job that runs the **previous release's** smoke tests against a DB migrated to the new head — the only *empirical* proof of old-code/new-schema compatibility. The gold standard if classifier+marker discipline ever proves insufficient.
  Together these are the **sole DB safety net**; auto-rollback can revert code, never data.

### 4.5.1 Rollback model (operational — the actual mechanics)

**Schema changes do NOT block automated releases.** The common case — additive migrations (new model/field/index, nullable or defaulted) — is *not* flagged, needs *no* marker, and ships through the normal automated tag→deploy pipeline with zero ceremony. A required marker is a one-line comment written *when authoring the migration*, reviewed in the same PR, and carried through the *same* automated pipeline — it is not a manual deploy step. CI blocks only a migration that is *unsafe as written* (an unmarked destructive op) — on a single prod box with no staging that is precisely the latent data-loss bug you want stopped, not friction. The discipline below is authoring-time; the release stays automated.

There is **no schema rollback**. Rollback = code-only (repoint `current` → `evennia reload`); schema only ever moves forward. Safety is an invariant, not migration reversal:

> **Invariant:** at every instant the live schema is compatible with *both* the current code release and the immediately-previous one.

Hold that and code-rollback is always sufficient. By operation class:

- **Additive (add column/table/index):** nullable or DB-default; ship migration with or before the code; old code ignores it. Mark `expand`. Trivial — genuinely solved.
- **Destructive (drop column/table):** split across **two** releases. Release N: code stops using it, *no drop*. Release N+1: migration drops it — the only rollback target (N) already doesn't need it. The destructive migration always ships *one release later* than the code change that freed it; `# release-safety: contract — superseded by vN` asserts exactly this and the reviewer's job is to verify the rollback target doesn't use it. (This temporal split is the entire trick — the answer the question "how do we roll back a schema change" never reaches because the real answer is "restructure so you never need to.")
- **Rename / add NOT NULL / type change:** parallel-change across releases (add new → backfill → dual-write → switch reads → drop old) **or** an accepted brief scheduled maintenance window. For a solo/cost-bound project a short window for a rare rename is a legitimate, cheaper choice than building dual-write machinery — stated explicitly, not pretended away.
- **Data migrations (`RunPython`):** forward-only, idempotent; reverse is **not** the safety net. Safety = the apply-against-restored-prod dry-run (catch pre-prod) + the backup (restore, accepting RPO, if it reaches prod). A bad data migration is prevented or restored-from, never "rolled back".
- **`evennia reload` overlap:** old and new code run concurrently for seconds during reload, so the migration must also be compatible with the *still-running old code* — run the (expand-only) migration, *then* reload; never ship a contract migration old code still needs.

**Irreducible backstop:** a catastrophic data migration that reaches prod is recovered only by restore-from-backup at the accepted ~24h RPO (§12). No free lunch — any process claiming schema changes are freely reversible is wrong.

### 4.6 Ephemeral staging
`tofu apply` a stage box from the latest backup → scripted sanity tests → on success promote → `tofu destroy`. Wrapped so teardown runs even on failure (trap/`finally`) — a failed test cannot leave a box running. Cost: Linode bills hourly capped monthly; a 30–60 min run is pennies. Billing stops on **delete, not power-off** — `tofu destroy` enforces this. A Linode billing alert is a cheap backstop.

### 4.7 DNS
Linode DNS managed as code in the same OpenTofu codebase. Arx II uses its **own new domain** (exact string is an implementation parameter, TBD; not a design blocker). Prod record carries a low TTL; `tofu apply` updates instance + A record atomically on rebuild. The ephemeral stage box uses a raw IP (no DNS). Arx I's existing domain is untouched by this sub-project.

### 4.8 Credentials & blast-radius model

**Credential boundary.** The Linode API token (`tofu` provider auth) lives **only** as a GitHub Actions secret bound to the gated `prod` GitHub Environment (required reviewers + branch restriction); injected solely into the deploy job, never the build/test job, never on any developer machine. No human or local agent holds a prod-capable token, so a local/errant process has no credential to reach Linode at all. *Honest limit:* Linode tokens scope by resource **type**, not instance — a token that can create prod can destroy it; the guarantee comes from *where the token lives and what may invoke it*, not token scoping. Third-party Actions pinned by SHA; workflow-file changes require review (prevents a slipped-in secret-exfil step).

**Blast-radius boundary (structural, not a flag).** Prod and ephemeral-stage are **separate root modules with separate state backends, separate state keys, and separate credential scope**. *"Separate credential scope" explicitly includes the Object Storage state-backend credential, not only the Linode API token:* prod and stage state keys may share one bucket family (§4.3), so the stage context's object-storage credential is scoped to only the stage state key/prefix (no read/list on the prod state key). Separate state keys alone are necessary but **not** sufficient — same-bucket keys are enumerable with a broad enough bucket credential; the scoped credential is what makes the isolation structural. `tofu destroy` only affects the state it is pointed at; the ephemeral-stage execution context contains *no prod state and no prod credentials*, so it **cannot enumerate or destroy prod by construction**. Prod's stateful resources (instance, volume, bucket) additionally carry `lifecycle { prevent_destroy = true }`. **No CI/automation path runs `tofu destroy` against prod state** — destroying prod is by design only a deliberate, manual, separately-authenticated, out-of-band human action; there is nothing automated to misfire.

**Ephemeral teardown targeting.** Each stage box uses a per-run-unique state key; the stage root module provisions only stage resources (no data sources reaching prod). The trap/`finally` teardown (§4.6) runs `tofu destroy` in the stage module against that per-run state and refuses unless resources are tagged `env=ephemeral-stage` — belt-and-suspenders over the state isolation. A stage run erroring mid-way still cannot target prod.

**Threat model (honest).** The above defends decisively against *accidents and errant automation/agents* (the stated threat) because state+credential isolation is a true structural boundary. It is **not** a defense against an authorized human who edits the code to remove `prevent_destroy`/guards and pushes it through review — the correct, accepted threat model here is guarding misfires, not authorized intentional destruction.

## 5. Data & Control Flow

- **Deploy:** tag → CI build/test/artifact → approval gate → Ansible (migrate with expand/contract + dry-run → unpack release → repoint `current` → `evennia reload`) → health gate → success or auto code-rollback.
- **Metrics:** in-process sampler → `/metrics` → Prometheus scrape → Grafana dashboards + alert rules; off-box heartbeat independently alerts on total-box failure.
- **Disaster recovery / clone:** `tofu apply` (provision) → Ansible restore-from-backup role (pull latest dump, restore, start) → a usable box, including the ephemeral-stage and migration-rehearsal use cases.

## 6. Failure Modes & Handling

| Failure | Handling |
|---|---|
| Bad release (import error, crash) | Health gate fails → auto code-rollback via symlink |
| Non-backward-compatible migration | CI gate fails the build; dry-run-against-restore catches data issues pre-prod |
| Game process leak / OOM | `MemoryMax` bounces only the game service; Postgres survives in its own cgroup |
| Whole box down | Off-box heartbeat fires an alert even though on-box Grafana is also down |
| State file lost | State in Object Storage, not local; recoverable |
| Forgotten stage box | Scripted `tofu destroy` (trap) + hourly-capped billing + billing alert |

## 7. Testing Strategy

- CI runs the existing arxii test suite + the §4.5 expand/contract classifier on every tagged build.
- Migration dry-run executes against a fresh restore of the prod DB before any prod migration.
- Ephemeral stage runs scripted smoke/sanity tests against a backup-restored environment before promotion.
- The observability layer itself is partly the production correctness test: the post-deploy health gate is metrics-driven.

## 8. Repo Layout (monorepo, `arxii`)

```
arxii/
  infra/
    terraform/      # OpenTofu: instance, volume, firewall, dns, bucket; remote state
    ansible/        # provision + deploy roles (restore-from-backup; later: legacy container)
    README.md       # operational runbook
  .github/workflows/  # tag-triggered build/test/deploy
  docs/superpowers/specs/   # this spec
  src/                # Arx II code; observability exporter module
```

Work proceeds on branch `infra/observability-baseline` (worktree off `main`).

## 9. Sequencing

This sub-project is a hard prerequisite for the Arx I legacy relocation (sub-project #2): it establishes the modern host, IaC, Caddy, and observability that the frozen legacy container co-resides on/behind.

## 10. Open Parameters (implementation-time, not design blockers)
- Arx II domain string.
- Exact Linode plan/region.
- Concrete metric thresholds for alert rules (tuned from first real data).

## 11. Acceptance Criteria

1. `tofu apply` + `ansible-playbook site.yml` from zero produces a working Arx II box (Postgres, Caddy TLS, game process under systemd) with no manual steps.
2. A semver release tag (`v1.2.3-release`) triggers CI → gated → deploy via `evennia reload` with connected players not dropped for a code-only change; `very-cool-tag`, bare `v1.2.3`, and non-semver `v1.2-release` trigger **no** deploy.
3. A migration with an unmarked destructive op (e.g. `RemoveField`) fails the CI classifier; the same migration with an explicit `# release-safety:` marker passes; an intentionally-irreversible data migration (no reverse, by design) is **not** flagged.
4. A simulated bad release auto-rolls-back on the health gate.
5. Grafana shows idmapper cache size/slope, reactor lag, and per-subsystem timing; an induced reactor stall is visible; flows-vs-scripts cost is readable from real data.
6. Killing the box triggers the off-box heartbeat alert.
7. `tofu apply` from a backup yields a restored clone usable as ephemeral stage; scripted teardown leaves nothing running.
8. The ephemeral-stage execution context provably has no prod state and no prod credentials; an attempted `tofu destroy` there cannot reference any prod resource. Teardown refuses to run unless resources are tagged `env=ephemeral-stage`.
9. `prevent_destroy` on prod stateful resources blocks an accidental/automated destroy; no pipeline or script path invokes `tofu destroy` against prod state. The Linode token exists only as a gated GitHub Environment secret and on no developer machine.

## 12. Honest Risks & Accepted Tradeoffs

- **Single box, thin safety nets** — accepted for cost (Arx I parity). Mitigations: ephemeral on-demand stage, off-box heartbeat, MemoryMax isolation.
- **Prod-destruction guards stop misfires, not authorized humans** — state/credential isolation + `prevent_destroy` + no-destroy-automation defend against accidents and errant agents (the real threat), not against an authorized operator who deletes the guards in a reviewed PR. Accepted threat model (§4.8).
- **Migration discipline is the sole DB safety net** — no always-on staging means expand/contract + dry-run is mandatory, enforced in CI, not a convention.
- **Nightly `pg_dump` ⇒ RPO ~24h** on full-box loss — accepted; WAL archiving is a named, deferred lever.
- **Co-resident monitoring blind spot** — Grafana dies with the box; mitigated (not eliminated) by the off-box heartbeat.
- This sub-project does **not** improve raw scaling. That is intentional and explicit; it produces the data to make those decisions later.
