# main uses a GitHub merge queue + single-leaf migration guard

`main` lands work through GitHub's native merge queue (squash), which re-tests each PR on top of the
latest main before merging, and `django-linear-migrations`' `max_migration.txt` surfaces cross-PR
migration collisions as an ordinary git conflict; we rejected manual re-sync cascades. The queue plus
the single-leaf guard keeps parallel PRs from silently colliding on migration order.

> Status: accepted · Source: #991
