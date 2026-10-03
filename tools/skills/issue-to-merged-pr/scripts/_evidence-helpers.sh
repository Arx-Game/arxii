# shellcheck shell=bash
# Shared by pickup-issue.sh, open-pr.sh and enqueue-pr.sh: when an issue needs a
# validated review-evidence report. Two signals, either is enough:
#   - the `review:evidence-required` label (applied at pickup, or by hand);
#   - a demo link in the issue body. A spec approved off a demo page is exactly
#     the work the demo-fidelity gate exists for (CLAUDE.md, "Demo fidelity"),
#     and #4098/#4099/#4101 slipped through because they carried a demo but not
#     the `frontend` label the gate used to key on (#4125).
# Keyed on the body, not only the label, so an issue picked up before the label
# existed, or labelled by hand without it, is still gated at open and enqueue.

DEMO_LINK_PATTERN='https://claude\.ai/(code/)?artifact/[A-Za-z0-9-]+'

# issue_body_has_demo_link <body>
issue_body_has_demo_link() {
  grep -qE "$DEMO_LINK_PATTERN" <<<"$1"
}

# evidence_required <labels-newline-separated> <body>
evidence_required() {
  if grep -qx "review:evidence-required" <<<"$1"; then
    return 0
  fi
  issue_body_has_demo_link "$2"
}
