"""Per-character display/visibility settings serializers (#1484, #1463).

The web control surface over ``TenureDisplaySettings.appear_offline`` (quiet/hidden mode). The
write goes through ``roster.services.display.set_appear_offline`` — this serializer only shapes
the request/response.
"""

from rest_framework import serializers


class VisibilitySettingsSerializer(serializers.Serializer):
    """The active character's own visibility prefs (#1484). Starts with ``appear_offline``.

    Read-and-write of quiet/hidden mode for the requesting player's active character. The
    fine-grained advanced controls (``show_online_status`` / ``allow_pages`` / ``allow_tells``)
    can join this surface later; the model already carries them.
    """

    appear_offline = serializers.BooleanField()
