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

# Disable debug mode for tests to avoid debug toolbar overhead
DEBUG = False

# Disable email sending during tests
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Disable external services during tests
SENDGRID_API_KEY = ""
CLOUDINARY_CLOUD_NAME = ""
CLOUDINARY_API_KEY = ""
CLOUDINARY_API_SECRET = ""
