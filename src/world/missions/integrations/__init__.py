"""Stub-seam modules for downstream reward delivery (Phase 5b.1).

Each sink (money, beat, rumor, crime-watch) is a separately-deferred
subsystem. The :func:`apply_deed_rewards` router routes by ``(kind, sink)``
to the matching stub. ``money_stub`` and ``beat_stub`` *record* calls (the
real subsystems will replace them); ``rumor_stub`` and ``crime_watch_stub``
*raise* NotImplementedError with a DESIGN reference because the upstream
systems do not exist yet — any mission emitting those lines must fail
loudly during apply.
"""
