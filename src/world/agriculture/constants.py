"""Constants for the agriculture system."""

FOOD_COLLECTION_CHECK_NAME = "Food Collection"

#: Base difficulty label for food collection checks (#2218). Pool size and
#: reactive triggers may escalate this. PLACEHOLDER — tune via admin or data.
FOOD_COLLECTION_BASE_DIFFICULTY = "normal"

#: Max level for the Field RoomFeatureKind.
FIELD_MAX_LEVEL = 5

#: Max level for the Granary RoomFeatureKind.
GRANARY_MAX_LEVEL = 5

#: Unrest skims the food haul on collection (#2238) — chaos and disrupted labor
#: lose food on the way in. Percent skimmed = min(this cap, domain.unrest). PLACEHOLDER.
UNREST_COLLECTION_SKIM_MAX_PCT = 60
