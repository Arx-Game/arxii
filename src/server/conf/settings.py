r"""
Evennia settings file.

The available options are found in the default settings file found
here:

https://www.evennia.com/docs/latest/Setup/Settings-Default.html

We diverge slightly from Evennia's conventions. I feel very
strongly that a secret settings file is an anti-pattern: you should
never have executable code live outside of version control.

Instead, we use the 12-factor app approach of having code and configuration
be decoupled, using django-environ library to have environment-specific
settings defined in an .env file that lives outside version control.

https://www.12factor.net/
https://github.com/joke2k/django-environ
"""

import contextlib
from email.utils import formataddr, parseaddr

import environ
from evennia.settings_default import *

env = environ.Env(
    # set casting, default value
    DEBUG=(bool, False),
)

# Take environment variables from .env file
environ.Env.read_env(os.path.join(GAME_DIR, ".env"))

# False if not in os.environ because of casting above
DEBUG = env("DEBUG")

# Raises Django's ImproperlyConfigured
# exception if SECRET_KEY not in os.environ
SECRET_KEY = env("SECRET_KEY")

# Parse database connection url strings
# like psql://user:pass@127.0.0.1:8458/db
DATABASES = {
    # read os.environ['DATABASE_URL'] and raises
    # ImproperlyConfigured exception if not found
    "default": env.db(),
}

INSTALLED_APPS += [
    # ORDER IS LOAD-BEARING between these two (#2885). Both apps ship a
    # `makemigrations` command, and Django's get_commands() walks
    # `reversed(apps.get_app_configs())` calling dict.update() — so the app
    # listed EARLIEST here wins, not the latest. core_management must therefore
    # come first for its phantom-Evennia-migration filter to run at all; it
    # subclasses django_linear_migrations' command, so the #991 sentinel below
    # still applies. Listed the other way round, the filter is silently inert
    # and every generated migration depends on a phantom Evennia migration that
    # exists only in the venv that made it. `core_management.tests
    # .test_command_resolution` pins this — don't reorder without reading it.
    "core_management",  # Add our management app for custom commands
    # Enforces one migration leaf per app via a per-app max_migration.txt
    # sentinel (#991). Two parallel branches that each add a migration both
    # bump that file, so the second surfaces as a git conflict at PR time
    # instead of a silent "multiple leaf nodes" failure in the merge queue.
    "django_linear_migrations",
    "web.admin.apps.AdminConfig",  # Custom admin functionality
    "flows.apps.FlowsConfig",
    "actions.apps.ActionsConfig",
    "world.apps.ArxiiConfig",
    "behaviors.apps.BehaviorsConfig",
    "drf_spectacular",
    "cloudinary",
    "allauth",
    "allauth.account",
    "allauth.headless",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.facebook",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.discord",
    # Load after allauth to override admin
    "evennia_extensions.apps.EvenniaExtensionsConfig",
    "django_htmx",
]

######################################################################
# Evennia base server config
######################################################################

# This is the name of your game. Make it catchy!
SERVERNAME = "Arx"
EVENNIA_ADMIN = False
MULTISESSION_MODE = 2
AUTO_CREATE_CHARACTER_WITH_ACCOUNT = False
AUTO_PUPPET_ON_LOGIN = False
IN_GAME_ERRORS = DEBUG

# Ensure the Evennia log directory exists for all environments (including CI).
LOG_DIR = os.path.join(GAME_DIR, "server", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Required for django-allauth
SITE_ID = os.environ.get("SITE_ID", 1)

# Add allauth middleware
MIDDLEWARE += [
    "allauth.account.middleware.AccountMiddleware",
    "evennia.web.utils.middleware.SharedLoginMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

# Enable webclient
WEBCLIENT_ENABLED = True

# Custom WebSocket client that reads session from cookies instead of URL parameters
WEBSOCKET_PROTOCOL_CLASS = "server.portal.secure_websocket.SecureWebSocketClient"

######################################################################
# Third-party integrations
######################################################################

# Cloudinary configuration for media storage
import cloudinary
import cloudinary.api
import cloudinary.uploader

cloudinary.config(
    cloud_name=env("CLOUDINARY_CLOUD_NAME", default=""),
    api_key=env("CLOUDINARY_API_KEY", default=""),
    api_secret=env("CLOUDINARY_API_SECRET", default=""),
)

# Email configuration
#
# RESEND_API_KEY is always read into a real setting: ResendAPIEmailBackend
# reads it from `settings.RESEND_API_KEY` at send time, not from `env()`
# directly (the backend has no import-time access to this file's `env`
# object).
RESEND_API_KEY = env("RESEND_API_KEY", default="")

if RESEND_API_KEY and not DEBUG:
    # Use Resend's HTTPS API for email delivery in production only.
    #
    # This used to be Django's SMTP backend against smtp.resend.com:587, but
    # the production host's upstream provider blocks outbound SMTP (587 and
    # 465, both timing out on smtp.resend.com AND smtp.gmail.com -- a
    # provider-level policy, not something in our control). That timeout
    # surfaced as an HTTP 500 on the signup endpoint, because allauth sends a
    # verification email inline with account creation. Port 443 to
    # api.resend.com is open, so ResendAPIEmailBackend sends over Resend's
    # HTTPS API instead. See ADR-0216.
    #
    # In DEBUG mode, always use the console backend instead, so no real mail
    # is sent in development -- the verification key prints to the server
    # log, where it can be extracted for manual or automated testing.
    EMAIL_BACKEND = "world.roster.email_backend.ResendAPIEmailBackend"
else:
    # Use console backend for testing when no email service configured
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
# Gmail and most other clients show a From address that has no display name as
# just its mailbox ("noreply"), so a bare address from the environment gets the
# game's name here. An operator who already supplies "Name <addr>" keeps it.
_from_email = env("DEFAULT_FROM_EMAIL", default="noreply@arx2.com")
DEFAULT_FROM_EMAIL = (
    _from_email if parseaddr(_from_email)[0] else formataddr(("Arx II", _from_email))
)
SITE_URL = env("SITE_URL", default="https://arxmush.org")

# systemd writes this file when a shutdown/reboot is scheduled and removes it on
# cancel; world.downtime derives the automatic-reboot announcement from it (#3194).
SCHEDULED_SHUTDOWN_FILE = env("SCHEDULED_SHUTDOWN_FILE", default="/run/systemd/shutdown/scheduled")

# Idmapper cache ceiling in MB (#3200). Stated explicitly rather than inherited.
#
# We used to take Evennia's settings_default value of 400 silently. That is a
# number nobody chose, on a box nobody measured it against, guarding the failure
# mode most likely to take this game down: Arx I ran on the 8 GB plan and
# SharedMemoryModel consumed all of it on a regular basis. Arx II runs on 4 GB
# with Postgres co-resident, and leans HARDER on the identity map (cached_property
# handlers hang off model instances throughout world/).
#
# 400 is kept as the value, now on purpose: idle Server RSS on prod measured
# ~156 MB (2026-08-16, no players, no content), so 400 leaves real working room
# while capping growth at roughly a tenth of the box. Raise it only with a
# measurement, and move offbox_rss_warn_mb (roles/offbox_alerting) up with it —
# the heartbeat alert must stay above this ceiling or routine flushes page us.
#
# How the ceiling is enforced, and its limits: Evennia's server_maintenance()
# runs every minute and calls conditional_flush, which flushes only when the
# cache count is above an estimated maximum AND RSS is already above 90% of this
# value. It is a last-ditch brake, not a governor. The cache-size estimate is
# openly a guess (`Ncache = |RMEM - 35.0| / 0.0157`, "empirically estimated from
# usage tests"), and a flush frees only what nothing else references — a
# module-level registry or long-lived service pinning instances defeats it.
# That is why #3200 pairs this with an external RSS alert instead of trusting it.
IDMAPPER_CACHE_MAXSIZE = env.int("ARXII_IDMAPPER_CACHE_MAXSIZE", default=400)

# Sample world content in the dev seeders (#2698). OFF by default.
#
# ``seed_dev_database()`` (the admin "Big Button") is mandatory — it is the only
# source of the game's mechanical spine (CheckRank, ResultChart, CheckOutcome,
# ConsequencePool, ActionTemplate, PointConversionRange, Pronouns, Heritage),
# none of which live in the content repo. But the same seeders also invented
# *named world content* — "House Veyrane PLACEHOLDER", "Great Archive
# Librarian", sample Beginnings/StartingAreas/Techniques — which
# ``export_to_content_repo`` then captured as though it were authored. That is
# how "Commoner", "Noble", "Arx City" and "Luxen Port" reached the content repo.
#
# With this off (the default), the Big Button seeds config only and invents no
# named content. Maintainers keep it off and author in the content repo. It
# exists for a future clone that has no content repo and needs a starter set;
# see #2698 for why that path is not yet complete.
SEED_SAMPLE_CONTENT = env.bool("ARXII_SEED_SAMPLE_CONTENT", default=False)

# Sentry error/performance monitoring (#2236 Phase 5). Optional: an empty DSN
# disables it entirely (dev/rehearsal have none), matching the ops dashboard's
# `sentry_dsn_configured` probe in `web/admin/tuning/tech_health.py`, which reads
# the same `SENTRY_DSN` env var. Deliberately separate from the bespoke, no-SaaS
# `SystemErrorReport` path (#1164, `world/player_submissions/services.py`) — that
# system stays player-facing and DB-backed by design; Sentry here is for
# ops/dev-facing infra-level error and performance telemetry.
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk  # deferred so DSN-less envs pay zero import cost

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        # PII off by design — player privacy is content-boundaries ADR territory;
        # Sentry must never capture request bodies, user emails, or IPs.
        send_default_pii=False,
        # Low sample rate: performance tracing is a sampling signal, not a full log.
        traces_sample_rate=float(env("SENTRY_TRACES_SAMPLE_RATE", default="0.05")),
        environment=env("SENTRY_ENVIRONMENT", default="production"),
        release=env("SENTRY_RELEASE", default="") or None,
    )

# GitHub issue filing (#1164) — staff can file a public issue from a player bug
# report or an auto-captured error. Repo + token are env-configured; an empty
# token disables the feature (the API surfaces it as unavailable rather than 500ing).
GITHUB_ISSUE_REPO = env("GITHUB_ISSUE_REPO", default="Arx-Game/arxii")
GITHUB_ISSUE_TOKEN = env("GITHUB_ISSUE_TOKEN", default=env("GH_TOKEN", default=""))

# Days a soft-deleted, non-lore-critical ItemInstance lingers (recoverable)
# before the daily cleanup hard-deletes it (#1025).
ITEM_SOFT_DELETE_GRACE_DAYS = env.int("ITEM_SOFT_DELETE_GRACE_DAYS", default=30)

# Fall-impact magnitude per elevation level descended during a plummet (#1228).
# The Plummeting ConditionInstance's severity accumulates one per round of
# descent; at impact, damage = severity * this value, routed through the
# standard survivability pipeline (process_damage_consequences).
FALL_IMPACT_PER_LEVEL = env.int("FALL_IMPACT_PER_LEVEL", default=5)

# Max ESTABLISHED personas (durable, reputation-bearing alter egos) a player may
# create per character via the designed creation flow (#1127). Staff bypass it.
# TEMPORARY masks are not capped here (throwaway). PLACEHOLDER magnitude.
MAX_ESTABLISHED_PERSONAS_PER_SHEET = env.int("MAX_ESTABLISHED_PERSONAS_PER_SHEET", default=5)

# Max number of exits a single travel_to dispatch will traverse in one go (#2163).
# Cross-Area BFS routing (#2223) has no separate Area-to-Area adjacency scoping —
# the exit graph alone is the connectivity, so this hop cap is the sole cost/reach
# bound against a pathological/disconnected-but-still-searched graph.
TRAVEL_MAX_HOPS = env.int("TRAVEL_MAX_HOPS", default=50)

# Overworld travel (#1855) — AP cost per IC hour of travel.
AP_PER_IC_HOUR = env.int("AP_PER_IC_HOUR", default=2)
# Overworld travel (#1855) — max hubs in a computed route.
OVERWORLD_MAX_HOPS = env.int("OVERWORLD_MAX_HOPS", default=20)

# Flat copper cost to install a portal anchor (e.g. a magic mirror) in a room
# the installer owns or has tenancy in (#2222). Deliberately cheap — a token
# cost, not a Project-scale grind (issue #2222 Decision 4).
PORTAL_ANCHOR_INSTALL_COST = env.int("PORTAL_ANCHOR_INSTALL_COST", default=5000)

# Max number of characters (drafts + owned) a non-staff account may hold at
# once, enforced by character_creation.services.can_create_character (#3046).
CG_MAX_CHARACTERS = env.int("CG_MAX_CHARACTERS", default=3)

# Web frontend base URL — the React app's origin. Referenced by allauth's
# headless redirect config below, CSRF_TRUSTED_ORIGINS, and telnet-side
# signposts (connection screen, characterless post-login message; #2122)
# so telnet players always have a pointer to the web front door.
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:3000")

# Django Allauth configuration
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Telnet-side account creation is closed alongside the web signup gate (#3054) —
# `create` is the only other account-creation door besides the web signup form,
# which the ArxAccountAdapter.is_open_for_signup override gates separately.
NEW_ACCOUNT_REGISTRATION_ENABLED = False

# Allauth settings
ACCOUNT_ADAPTER = "evennia_extensions.adapters.ArxAccountAdapter"
SOCIALACCOUNT_ADAPTER = "evennia_extensions.social_adapters.ArxSocialAccountAdapter"
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
# Without a prefix allauth falls back to "[<Site.name>] ", and the only row in
# Django's sites table is the framework default "example.com". The stock body
# templates read that same row; their overrides live in
# src/web/templates/account/email/. Same prefix the roster mail already uses.
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[Arx II] "
ACCOUNT_LOGIN_METHODS = {"username", "email"}  # Support both username and email login
ACCOUNT_SIGNUP_FIELDS = ["email*", "username*", "password1*", "password2*"]
LOGIN_REDIRECT_URL = "/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/"
ACCOUNT_EMAIL_CONFIRMATION_AUTHENTICATED_REDIRECT_URL = FRONTEND_URL + "/login?verified=true"

# Django-allauth headless configuration
HEADLESS_ONLY = True  # Use headless API mode with custom email verification
HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": FRONTEND_URL
    + "/verify-email/{key}",  # Go to frontend, which will call API
    "account_reset_password": FRONTEND_URL + "/reset-password",
    "account_reset_password_from_key": FRONTEND_URL + "/reset-password/{key}",
    "account_signup": FRONTEND_URL + "/signup",
}

# Social auth providers
SOCIALACCOUNT_PROVIDERS = {
    "facebook": {
        "METHOD": "oauth2",
        "SDK_URL": "//connect.facebook.net/{locale}/sdk.js",
        "SCOPE": ["email"],
        "AUTH_PARAMS": {"auth_type": "reauthenticate"},
        "INIT_PARAMS": {"cookie": True},
        "FIELDS": [
            "id",
            "first_name",
            "last_name",
            "middle_name",
            "name",
            "name_format",
            "picture",
            "short_name",
            "email",
        ],
        "EXCHANGE_TOKEN": True,
        "VERIFIED_EMAIL": False,
        "VERSION": "v18.0",
        "APP": {
            "client_id": env("FACEBOOK_APP_ID", default=""),
            "secret": env("FACEBOOK_APP_SECRET", default=""),
        },
    },
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "VERIFIED_EMAIL": True,  # Google emails are verified
        "APP": {
            "client_id": env("GOOGLE_CLIENT_ID", default=""),
            "secret": env("GOOGLE_CLIENT_SECRET", default=""),
        },
    },
    "discord": {
        "SCOPE": ["identify", "email"],
        "VERIFIED_EMAIL": True,  # Discord requires email verification for accounts
        "APP": {
            "client_id": env("DISCORD_CLIENT_ID", default=""),
            "secret": env("DISCORD_CLIENT_SECRET", default=""),
        },
    },
}

######################################################################
# Django REST Framework configuration
######################################################################

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "EXCEPTION_HANDLER": "web.api.exceptions.custom_exception_handler",
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Paginate every list endpoint by default (2026-07 audit) — a ViewSet must
    # explicitly `pagination_class = None` to return a bare array. See ADR-0138
    # and web/api/pagination.py.
    "DEFAULT_PAGINATION_CLASS": "web.api.pagination.DefaultPagination",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Arx API",
    "DESCRIPTION": "API for the Arx web interface",
    "VERSION": "0.1.0",
    "SCHEMA_PATH_PREFIX": r"/api/",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
    ],
    # Several models share a `visibility` field name with different choice
    # sets; without an override spectacular emits hash-suffixed collision
    # names (e.g. VisibilityBe1Enum) that churn whenever a new collision
    # appears. Pin ours explicitly.
    "ENUM_NAME_OVERRIDES": {
        "MissionVisibilityEnum": "world.missions.constants.MissionVisibility.choices",
        # Several serializers expose a `category` field from the same NarrativeCategory
        # choices (NarrativeMessage, NarrativeMessageDelivery, UserCategoryMute); without
        # this, spectacular emits a hash-suffixed collision name (CategoryF17Enum) that
        # churns whenever a new `category` field appears. Pin it (#1522).
        "NarrativeCategoryEnum": "world.narrative.constants.NarrativeCategory.choices",
        # ConsentMode is shared by SocialConsentCategoryRule.mode AND, since #2170,
        # SocialConsentCategory.default_mode. Without a pin, spectacular splits them into a
        # field-named enum plus a hash-suffixed collision name (Mode447Enum) that churns.
        "ConsentModeEnum": "world.consent.constants.ConsentMode.choices",
    },
}

# Patch django-filter 2.4.0 compatibility with Django 5.2.
# Django 5.2 replaced ChoiceField._set_choices/_get_choices with a property decorator.
# django-filter 2.4.0 (pinned by Evennia) still calls super()._set_choices() which no longer
# exists. This monkey-patch provides the missing method so schema generation and filter
# instantiation don't crash.
try:
    from django.forms.fields import ChoiceField as _DjangoChoiceField

    if not hasattr(_DjangoChoiceField, "_set_choices"):

        def _compat_set_choices(self, value):
            self._choices = self.widget.choices = value

        def _compat_get_choices(self):
            return self._choices

        _DjangoChoiceField._set_choices = _compat_set_choices  # type: ignore[attr-defined]  # noqa: SLF001
        _DjangoChoiceField._get_choices = _compat_get_choices  # type: ignore[attr-defined]  # noqa: SLF001
except Exception:  # noqa: BLE001, S110
    pass  # If API changed, skip silently

######################################################################
# Test configuration
######################################################################

# Custom test runner with timing information
TEST_RUNNER = "server.conf.test_runner.TimedEvenniaTestRunner"

######################################################################
# Logging configuration
######################################################################

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{levelname}] {asctime} {name} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "[{levelname}] {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "world": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "evennia": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

######################################################################
# Development environment configuration
######################################################################

# CSRF trusted origins - configurable via environment
CSRF_TRUSTED_ORIGINS = []

# Always allow local development
if DEBUG:
    CSRF_TRUSTED_ORIGINS.extend(
        [
            "http://localhost:5173",  # Vite dev server
            "http://127.0.0.1:5173",
            f"http://localhost:{env('DJANGO_PORT', default='4001')}",
        ],
    )

# Add frontend URL if specified (for ngrok, production domains, etc.)
# Kept as its own env() lookup (default="") rather than settings.FRONTEND_URL:
# FRONTEND_URL defaults to http://localhost:3000, but CSRF_TRUSTED_ORIGINS should
# only gain an entry when the operator has explicitly configured a frontend URL.
frontend_url = env("FRONTEND_URL", default="")
if frontend_url:
    CSRF_TRUSTED_ORIGINS.append(frontend_url)

# Add any additional trusted origins from environment
additional_origins = env("CSRF_TRUSTED_ORIGINS", default="")
if additional_origins:
    # Support comma-separated list
    CSRF_TRUSTED_ORIGINS.extend(
        [url.strip() for url in additional_origins.split(",") if url.strip()],
    )

######################################################################
# Custom admin site configuration
######################################################################

# Replace the default admin.site with our custom ArxAdminSite globally.
# This ensures all admin.register() calls throughout the codebase
# (including Evennia's built-in registrations) use our custom site.
#
# TIMING: This replacement happens at settings.py import time, which occurs
# BEFORE Django's admin.autodiscover() runs (autodiscover happens during URL
# resolution). Therefore, all @admin.register() decorators in admin.py files
# will use our custom site without requiring any changes to those files.
#
# Note: The imports below are absolute imports per project standards.
from django.contrib import admin

from web.admin import arx_admin_site

admin.site = arx_admin_site
admin.sites.site = arx_admin_site

######################################################################
# Production hardening overlay (optional)
######################################################################

# Rendered by Ansible (roles/django_hardening) on the prod box ONLY —
# gitignored (src/server/.gitignore), absent in dev/CI, so this import is a
# no-op everywhere except the production host. It contains NO secret VALUES
# (only env-reads via os.environ, sourced from the secrets_vault
# EnvironmentFile, plus a handful of prod-only booleans/lists that env()
# alone can't express — DEBUG, ALLOWED_HOSTS, cookie/proxy/SSL toggles,
# WEBSOCKET_CLIENT_URL, rate limits). SECRET_KEY, DATABASE_URL, the
# Cloudinary trio, RESEND_API_KEY, FRONTEND_URL, and SITE_URL are all
# already handled above by this file's own env() reads against that same
# EnvironmentFile — nothing here re-derives them. Importing LAST (star
# import, so anything it sets simply overrides the dev default set above)
# does NOT violate this file's stance against a secret-VALUES file living
# outside version control (see the module docstring) — it's an env-driven
# overlay, same 12-factor contract as the rest of this file.
with contextlib.suppress(ImportError):
    import server.conf.secret_settings as _secret_settings

    _public_names = (name for name in dir(_secret_settings) if not name.startswith("_"))
    globals().update({name: getattr(_secret_settings, name) for name in _public_names})
