# ADR-4999: systemd supervises the Portal, and a reload proves itself

**Status:** Accepted (2026-11-07, #4999). Narrows ADR-0318's watchdog; its `@shutdown` and
`@reboot` rules are unchanged.

The unit's `PIDFile` named the Server, so a reload whose replacement never came up stopped the
Portal as well, reported success, and read as a deliberate stop: the game stayed down until the
next deploy, twice in one week. `PIDFile` now names the Portal, the process that actually stays
up. `ExecReload` is `arxii-reload`, which counts as success only when a new Server answers on its
own port under the same Portal, and otherwise recovers the Server alone within 180 s. The script
never restarts the unit, because a restart from inside the reload job cancels that job. Its caller
owns the last resort: the deploy's rescue, or the watchdog, limited to one full restart per 15
minutes. A process is only ever signalled after its identity is proven by cgroup, user and command
line, whatever port it holds. `Account` now tells the Portal whenever a session takes up or lets go
of a character, because Evennia does so only during a graceful reload, and without it a crash left
players connected, logged in and silently out of character.

**Accepted costs.** A lone Server crash no longer reaches `Restart=on-failure`, so recovery can
begin up to about 105 s later, by the watchdog. A hard-killed Server loses anything unsaved, and none of
its reload or shutdown hooks run. A manual `evennia sstop` comes back.

**Rejected.** `ExitType=cgroup`, which the issue's isolated test first pointed at: `PIDFile` on the
Portal needs no new systemd setting, and real-systemd runs showed the Server's clean and unclean
exits both leave the unit alone. Full restart for a hung or crashed Server: simplest, but drops
every player when the Portal is healthy. Having the web client re-enter the character when the
Server announces a restart: a larger change that leaves telnet players stranded. Code rollback as a
further last resort: the schema has already moved forward by then. Proof lives in
`.github/workflows/reload-recovery.yml`, on real systemd, because neither the devcontainer nor a
shell fake can show this behaviour.
