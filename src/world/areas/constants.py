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
