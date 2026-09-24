"""Staff-requested full reboot of both Evennia daemons (#4001).

The game process runs as a user with no sudo, and ``Restart=always`` on the
unit was rejected because it would turn every ``@shutdown`` into a restart.
So a reboot is two things: a request file that the root watchdog (once a
minute, ``infra/ansible/roles/app_deploy/templates/arxii-watchdog.sh.j2``)
reads as "this inactive unit should come back", and the same Portal shutdown
``@shutdown`` performs. The file goes first: without it, the shutdown would
leave the game down.

Neither ``@reload`` (Server only; ``@restart`` is Evennia's alias for it) nor
``@shutdown`` (both daemons, stays down) does this.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from django.conf import settings
import evennia

logger = logging.getLogger(__name__)

# The watchdog template names the same path relative to ``app_gamedir``; the
# acceptance script checks the two spellings agree.
REBOOT_REQUEST_FILE = Path(settings.GAME_DIR) / "server" / "reboot.requested"


def request_reboot(*, requested_by: str) -> None:
    """Ask for a full reboot: record the request, tell everyone, shut down.

    Raises ``OSError`` without shutting anything down when the request file
    cannot be written, since that file is the only thing that brings the
    game back.
    """
    request_file = REBOOT_REQUEST_FILE
    request_file.parent.mkdir(parents=True, exist_ok=True)
    request_file.write_text(f"requested_by={requested_by}\n")
    # Flush to disk before the process goes away.
    with request_file.open("rb+") as handle:
        os.fsync(handle.fileno())
    logger.warning("Full reboot requested by %s; shutting down both daemons.", requested_by)
    handler = evennia.SESSION_HANDLER
    handler.announce_all(
        f"\nThe game is being restarted by {requested_by}. It will be back in a minute or two.\n"
    )
    handler.portal_shutdown()
