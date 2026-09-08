from django.db import models


class RealmTheme(models.TextChoices):
    DEFAULT = "default", "Default"
    ARX = "arx", "Arx"
    UMBROS = "umbros", "Umbros"
    LUXEN = "luxen", "Luxen"
    INFERNA = "inferna", "Inferna"
    ARIWN = "ariwn", "Ariwn"
    AYTHIRMOK = "aythirmok", "Aythirmok"


# The line every realm's testament opens on (#3725). One shared string, served in the realm
# payload so the page never carries lore of its own; the testament rows carry the rest.
TESTAMENT_THRESHOLD_LINE = "One stands before us in Durance. Speak thy name and testament."
