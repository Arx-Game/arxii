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
    DEBUG=(bool, False)
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
    "flows.apps.FlowsConfig",
    "evennia_extensions.apps.EvenniaExtensionsConfig",
    "world.roster.apps.RosterConfig",
    "world.traits.apps.TraitsConfig",
    "behaviors.apps.BehaviorsConfig",
    "cloudinary",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.facebook",
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

# Required for django-allauth
SITE_ID = os.environ.get("SITE_ID", 1)

# Add allauth middleware
MIDDLEWARE += [
    "allauth.account.middleware.AccountMiddleware",
]

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

# Email configuration with SendGrid
EMAIL_BACKEND = "sendgrid_backend.SendgridBackend"
SENDGRID_API_KEY = env("SENDGRID_API_KEY", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@arxmush.org")

# Django Allauth configuration
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Allauth settings
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_LOGIN_METHODS = ["email"]
ACCOUNT_SIGNUP_FIELDS = ["email*", "username*", "password1*", "password2*"]
LOGIN_REDIRECT_URL = "/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/"

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
    }
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
TEST_RUNNER = "server.conf.test_runner.TimedTestRunner"

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
