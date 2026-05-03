"""
Shim for Windows parallel test worker compatibility — production settings variant.

Mirrors src/test_settings.py. When arx test --production-settings is used,
Django sets DJANGO_SETTINGS_MODULE='settings'. Workers find this shim via the
editable install .pth that puts src/ on sys.path.
"""

from server.conf.settings import *
