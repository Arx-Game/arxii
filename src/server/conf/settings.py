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
