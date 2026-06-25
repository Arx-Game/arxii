# Feature specs live in the GitHub issue body, gated by labels

A feature spec lives between `spec:start`/`spec:end` markers in the GitHub issue body, and the
member-only `spec:approved` label is the authorization boundary on our public repo; spec files are not
committed. We rejected committed spec files and comment-based gating — comments can't gate because
anyone can comment, whereas only Triage+ org members can apply labels.

> Status: accepted · Source: CLAUDE.md
