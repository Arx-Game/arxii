# Staff config & game-tuning tooling is admin-hosted, not React

Superuser/staff configuration and game-tuning UI is built on django-unfold + HTMX, reusing the
existing admin RBAC, rather than in the React client; we rejected building it into the player
frontend. Staff tooling can lean on admin permissions and server-rendered forms, so it doesn't earn
the cost of bespoke React surfaces.

> Status: accepted · Source: #1220, memory
