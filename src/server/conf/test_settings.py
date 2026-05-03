"""
Test-specific settings for Arx II.

This file contains optimizations specifically for test runs to improve performance
while maintaining test accuracy. These settings should not be used in production.
"""

# Import all base settings
from server.conf.settings import *  # noqa: F403

# Use the same Postgres database as production — Django auto-creates a
# test_<dbname> copy.  This ensures Postgres-specific features (materialized
# views, recursive CTEs, etc.) are exercised in tests.
# Use `--keepdb` with `arx test` to reuse the test DB across runs.

# Use fast password hashing for tests (tests don't need secure passwords)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Reduce logging verbosity during tests
LOGGING["loggers"]["django.db.backends"]["level"] = "ERROR"
LOGGING["loggers"]["evennia"]["level"] = "ERROR"
LOGGING["loggers"]["django.request"]["level"] = "ERROR"

# Silence app-level INFO loggers that fire during normal operation — useful
# in production for ops visibility but pure noise in tests. Set to WARNING so
# unexpected ERROR-level events still surface.
# world.skills is set to ERROR because the noisy line is at WARNING level.
for _noisy_logger, _level in [
    ("world.game_clock", "WARNING"),
    ("world.progression", "WARNING"),
    ("world.fatigue", "WARNING"),
    ("world.skills", "ERROR"),
    ("flows.emit", "ERROR"),
]:
    LOGGING["loggers"].setdefault(
        _noisy_logger,
        {"handlers": ["console"], "propagate": False},
    )
    LOGGING["loggers"][_noisy_logger]["level"] = _level

# Disable debug mode for tests to avoid debug toolbar overhead
DEBUG = False

# Register integration test package so pipeline tests run with `arx test`
INSTALLED_APPS += ["integration_tests"]  # type: ignore[name-defined]

# Disable email sending during tests
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Tell Evennia we're in a test environment so it gracefully handles missing
# Limbo (the default home object). Without this, calls to create_object()
# fail with FK violations on db_home_id when Limbo doesn't exist (which is
# the case in fresh test DBs that haven't run Evennia's initial_setup).
TEST_ENVIRONMENT = True

# Disable external services during tests
SENDGRID_API_KEY = ""
CLOUDINARY_CLOUD_NAME = ""
CLOUDINARY_API_KEY = ""
CLOUDINARY_API_SECRET = ""
