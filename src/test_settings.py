"""
Shim for Windows parallel test worker compatibility.

On Windows, multiprocessing uses 'spawn' to create worker processes. Spawn workers
do not inherit sys.path mutations made by the parent (Evennia's launcher), but they
DO inherit environment variables including DJANGO_SETTINGS_MODULE. Django's management
layer sets DJANGO_SETTINGS_MODULE to the bare value passed to --settings (e.g.
'test_settings'), while Evennia's launcher builds the fully-qualified dotted path
(e.g. 'server.conf.test_settings') only in os.environ — which Django then overwrites.

This shim lives at src/test_settings.py (importable as 'test_settings' because src/
is on sys.path via the editable install .pth file). Workers use DJANGO_SETTINGS_MODULE
= 'test_settings', find this shim, and get the real settings through the re-export.
"""

from server.conf.test_settings import *  # noqa: F403
