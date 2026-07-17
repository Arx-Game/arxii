"""Shared stub content-repo root for tests exercising ``seed_dev_database()``.

``seed_dev_database()`` (#2474 Decision 5) now loads the arx2-lore content
repo before running any cluster seeder, and raises loudly (``ContentError``)
when ``CONTENT_REPO_PATH`` is unset or invalid — no silent skip, no
synthetic in-repo fallback. Every existing test in ``world.seeds.tests``
that calls ``seed_dev_database()`` needs a real (if minimal) content root on
disk for the duration of the call. This mirrors
``web.admin.tests.test_content_load_views``'s tmp-dir +
``CONTENT_REPO_PATH`` env-patch pattern, reused here rather than
reinvented — every ``seed_dev_database()`` caller in this package needs
exactly the same stub.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import tempfile
from unittest import mock

#: Name of the Trait row the stub fixture below creates — tests proving the
#: content load actually ran (not silently skipped) assert against this.
STUB_TRAIT_NAME = "Seed Test Stub Skill"

_STUB_SKILL_MD = f"""---
name: {STUB_TRAIT_NAME}
category: general
---
PLACEHOLDER stub content-repo skill; exists only so seed_dev_database()'s
tests have a minimal valid content root to load.
"""


@contextmanager
def stub_content_root() -> Iterator[Path]:
    """Build a tmp content root with one valid fixture; patch CONTENT_REPO_PATH.

    Usable as a context manager (``with stub_content_root():``) or, since a
    ``@contextmanager``-built generator function's return value doubles as a
    ``contextlib.ContextDecorator``, as a test-method decorator
    (``@stub_content_root()``) — each call/decoration gets its own fresh tmp
    dir, so it is safe to stack on multiple test methods in the same class.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        skill_path = root / "skills" / "stub.md"
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(_STUB_SKILL_MD, encoding="utf-8")
        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(root)}):
            yield root
