# One shared base per concept; no parallel implementations

Two parallel implementations of a single concept are tech debt, so siblings converge on a shared base
class or a downstream convergence model and share fields via Django abstract base classes; we rejected
per-sibling duplication. When a second implementation of the same idea appears, find the shared base
rather than letting both drift.

> Status: accepted · Source: memory
