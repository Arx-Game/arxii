# No Django signals; explicit service-function calls

State changes route through named service functions rather than `post_save`/`pre_delete` signal
handlers, so the control flow is explicit and testable at the call site; we rejected the idiomatic
Django signal pattern. Signals hide causation and make ordering and test setup fragile.

> Status: accepted · Source: CLAUDE.md
