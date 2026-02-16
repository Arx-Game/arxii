from django.db import models


class RealmTheme(models.TextChoices):
    DEFAULT = "default", "Default"
    ARX = "arx", "Arx"
    UMBROS = "umbros", "Umbros"
    LUXEN = "luxen", "Luxen"
    INFERNA = "inferna", "Inferna"
    ARIWN = "ariwn", "Ariwn"
    AYTHIRMOK = "aythirmok", "Aythirmok"
