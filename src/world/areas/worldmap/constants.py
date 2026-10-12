"""Vocabulary of the world map (#4242).

A pip is a 10-mile square; ten pips a side make the 100-mile cell the Atlas
views the map through. Everything stored is pips; the cell is only a lens
(ApostateCD's rulings on #4242, 2026-10-11).
"""

from django.db import models

PIPS_PER_CELL = 10
MILES_PER_PIP = 10

# The generator's height scale: 0-100, sea below 20, mountains from 71 (its
# relief rules), hills 50-70.
GENERATOR_SEA_LEVEL = 20
GENERATOR_HILL_HEIGHT = 50
GENERATOR_MOUNTAIN_HEIGHT = 71


class Terrain(models.TextChoices):
    """What one pip of ground is. Geography, not combat terrain: the battles app's
    ``TerrainType`` is a battlefield's tactical shape and shares nothing with this.

    The coast is not a member: a coast is land next to water, and the renderer
    reads it from the neighbours rather than storing a copy.
    """

    WATER = "water", "Water"
    LAKE = "lake", "Lake"
    PLAIN = "plain", "Plain"
    FOREST = "forest", "Forest"
    HILL = "hill", "Hill"
    MOUNTAIN = "mountain", "Mountain"
    MARSH = "marsh", "Marsh"
    DESERT = "desert", "Desert"
    TUNDRA = "tundra", "Tundra"
    GLACIER = "glacier", "Glacier"


WATER_TERRAINS = frozenset({Terrain.WATER, Terrain.LAKE})


class PipSource(models.TextChoices):
    """Who last said what a pip is. A re-rasterize rewrites only the generator's
    pips; a staff member's paint survives every upload (ruling 5, #4242).
    """

    GENERATOR = "generator", "Generator"
    STAFF = "staff", "Staff"
