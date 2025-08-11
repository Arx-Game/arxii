from django.db import models


class MessageContext(models.TextChoices):
    PUBLIC = "public", "Public"
    TABLETALK = "tabletalk", "Tabletalk"
    PRIVATE = "private", "Private"


class MessageMode(models.TextChoices):
    POSE = "pose", "Pose"
    EMIT = "emit", "Emit"
    SAY = "say", "Say"
    WHISPER = "whisper", "Whisper"
    OOC = "ooc", "OOC"
