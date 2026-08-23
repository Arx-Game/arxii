"""Constants for the boards system (#3286)."""

#: Default cap on how many active (non-removed) posts a board displays. Older
#: posts fall off the display but are retained in the DB (no hard-delete).
DEFAULT_MAX_ACTIVE_POSTS = 30
