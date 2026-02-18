"""Tarot system constants."""

from django.db import models


class ArcanaType(models.TextChoices):
    MAJOR = "major", "Major Arcana"
    MINOR = "minor", "Minor Arcana"


class TarotSuit(models.TextChoices):
    SWORDS = "swords", "Swords"
    CUPS = "cups", "Cups"
    WANDS = "wands", "Wands"
    COINS = "coins", "Coins"


SUIT_SINGULAR = {
    TarotSuit.SWORDS: "Sword",
    TarotSuit.CUPS: "Cup",
    TarotSuit.WANDS: "Wand",
    TarotSuit.COINS: "Coin",
}
