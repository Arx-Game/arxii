from django.db import models


class AreaLevel(models.IntegerChoices):
    BUILDING = 10, "Building"
    NEIGHBORHOOD = 20, "Neighborhood"
    WARD = 30, "Ward"
    CITY = 40, "City"
    REGION = 50, "Region"
    KINGDOM = 60, "Kingdom"
    CONTINENT = 70, "Continent"
    WORLD = 80, "World"
    PLANE = 90, "Plane"


# Area quality ladder (PLACEHOLDER labels, staff-tunable).
AREA_QUALITY_MIN = 0
AREA_QUALITY_MAX = 5
AREA_QUALITY_NORMAL = 3

AREA_QUALITY_LABELS: dict[int, str] = {
    0: "Blighted",
    1: "Neglected",
    2: "Rundown",
    3: "Ordinary",
    4: "Tidy",
    5: "Pristine",
}

# Above-normal quality decays one step after this many days.
CLEANUP_DWELL_DAYS = 7
# Below-normal quality recovers one step per this many weeks.
CLEANUP_REGAIN_WEEKS = 2
# Default project period in days.
CLEANUP_PROJECT_DAYS = 30
# Quality lost per crime/combat erosion event.
CLEANUP_EROSION_AMOUNT = 1
# Society reputation granted per contribution to a cleanup project.
CLEANUP_SOCIETY_REPUTATION_DELTA = 10
