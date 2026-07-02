"""Integration modules for downstream reward delivery (Phase 5b.1+).

The :func:`apply_deed_rewards` router routes by ``(kind, sink)`` to the
matching module. ``money_stub`` and ``beat_stub`` *record* calls (the real
subsystems will replace them); ``rumor_stub`` *raises* NotImplementedError
with a DESIGN reference because the rumor system does not exist yet — any
mission emitting those lines must fail loudly during apply. ``crime_watch``
is live (#1765): it mints pursuit heat + the society sting via the justice
app.
"""
