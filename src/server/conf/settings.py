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
    "core_management",  # Add our management app for custom commands
    "flows.apps.FlowsConfig",
    "world.roster.apps.RosterConfig",
    "world.traits.apps.TraitsConfig",
    "world.character_sheets.apps.CharacterSheetsConfig",
    "world.classes.apps.ClassesConfig",
    "world.progression.apps.ProgressionConfig",
    "world.scenes.apps.ScenesConfig",
    "world.stories.apps.StoriesConfig",
    "behaviors.apps.BehaviorsConfig",
    "cloudinary",
    "allauth",
    "allauth.account",
    "allauth.headless",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.facebook",
    # Load after allauth to override admin
    "evennia_extensions.apps.EvenniaExtensionsConfig",
]

######################################################################
# Evennia base server config
######################################################################

# This is the name of your game. Make it catchy!
SERVERNAME = "Arx II"
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
if env("RESEND_API_KEY", default=""):
    # Use Resend for email delivery
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = "smtp.resend.com"
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = "resend"
    EMAIL_HOST_PASSWORD = env("RESEND_API_KEY")
else:
    # Use console backend for testing when no email service configured
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@arxmush.org")

# Django Allauth configuration
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Allauth settings
ACCOUNT_ADAPTER = "evennia_extensions.adapters.ArxAccountAdapter"
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_LOGIN_METHODS = {"username", "email"}  # Support both username and email login
ACCOUNT_SIGNUP_FIELDS = ["email*", "username*", "password1*", "password2*"]
LOGIN_REDIRECT_URL = "/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/"
ACCOUNT_EMAIL_CONFIRMATION_AUTHENTICATED_REDIRECT_URL = (
    env("FRONTEND_URL", default="http://localhost:3000") + "/login?verified=true"
)

# Django-allauth headless configuration
HEADLESS_ONLY = True  # Use headless API mode with custom email verification
HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": env("FRONTEND_URL", default="http://localhost:3000")
    + "/verify-email/{key}",  # Go to frontend, which will call API
    "account_reset_password": env("FRONTEND_URL", default="http://localhost:3000")
    + "/reset-password",
    "account_reset_password_from_key": env(
        "FRONTEND_URL",
        default="http://localhost:3000",
    )
    + "/reset-password/{key}",
    "account_signup": env("FRONTEND_URL", default="http://localhost:3000") + "/signup",
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
        "LOCALE_FUNC": "path.to.callable",
        "VERIFIED_EMAIL": False,
        "VERSION": "v18.0",
        "APP": {
            "client_id": env("FACEBOOK_APP_ID", default=""),
            "secret": env("FACEBOOK_APP_SECRET", default=""),
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
}

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
