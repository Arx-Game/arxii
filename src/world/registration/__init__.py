"""Invitation-gated account registration (#3054).

Registration is closed by default: ``RegistrationConfig`` is a DB singleton
staff flip to open it operationally, no deploy required (mirrors
``world.scenes.models.SceneRoundDefaultsConfig``). While closed, a visitor
needs a staff-issued, per-email single-use ``AccountInvite`` — see
``docs/systems/registration.md`` for the full design and
``evennia_extensions.adapters.ArxAccountAdapter.is_open_for_signup`` for the
allauth seam that enforces the gate.
"""
