"""Choices for the houses system (#1884)."""

from django.db import models

# --- Domain economics (#2238) — PLACEHOLDER magnitudes ---
# Prosperity at which a domain's holdings yield their base gross (a neutral 1.0x).
# Above it holdings over-yield; below they under-yield; at 0 prosperity, no income.
DOMAIN_PROSPERITY_BASELINE = 50

# Unrest above this threshold can boil over into a DomainCrisis on the weekly tick;
# each point above it adds UNREST_CRISIS_PCT_PER_POINT% to the weekly chance.
UNREST_CRISIS_THRESHOLD = 60
UNREST_CRISIS_PCT_PER_POINT = 2


class TitleTier(models.TextChoices):
    """Rank of a landed/dynastic title. Realm-specific display labels are
    authorable on the Title row itself; this is the mechanical ladder."""

    CROWN = "crown", "Crown"
    DUCHY = "duchy", "Duchy"
    COUNTY = "county", "County"
    BARONY = "barony", "Barony"


class RecognitionRuleKind(models.TextChoices):
    """Per-realm house-recognition rules (#1884, Apostate lore rulings).

    Umbral matrilineality: a noblewoman's in-wedlock children are recognized
    automatically; out of wedlock it is the mother's option; a nobleman's
    children by a commoner woman belong to HER family (commoner, not
    bastard). Inferna ennobles the female titleholder's children by male
    consorts.
    """

    MATRILINEAL_AUTO_WEDLOCK = "matrilineal_auto_wedlock", "Matrilineal (auto in wedlock)"
    MOTHER_OPTION_OUT_OF_WEDLOCK = "mother_option", "Mother's option (out of wedlock)"
    CONSORT_CHILDREN_ENNOBLED = "consort_ennobled", "Titleholder's consort children ennobled"
    PATRILINEAL_AUTO_WEDLOCK = "patrilineal_auto_wedlock", "Patrilineal (auto in wedlock)"


class SuccessionDerivation(models.TextChoices):
    """How the candidate set derives from the kinship graph (#1884)."""

    PRIMOGENITURE_WEDLOCK = "primogeniture_wedlock", "Eldest legitimate child"
    MATRILINEAL_RECOGNITION = "matrilineal_recognition", "Recognized matrilineal issue"
    FEMALE_LINE_CONSORTS_ENNOBLED = "female_line", "Female-line issue (consorts ennobled)"
    CHOSEN_HEIR = "chosen_heir", "Chosen heir"
    TANISTRY_ELECTION = "tanistry_election", "Tanistry election"


class SuccessionOrdering(models.TextChoices):
    """How candidates are ranked (#1884). MOST_POWERFUL_GIFTED resolves via a
    pluggable registry with a PLACEHOLDER proxy — never hardcoded."""

    ELDEST = "eldest", "Eldest first"
    MOST_POWERFUL_GIFTED = "most_powerful_gifted", "Most powerful Gifted first"


class PactCommitmentKind(models.TextChoices):
    """Coded marriage-pact commitments that fire mechanically (#1884).

    DOWRY: one-time treasury transfer at signing. SUBSIDY: recurring
    OrgObligation from senior to junior house. CRISIS_RESPONSE: the
    committed person is auto-invited into the ally's crisis content.
    RESIDENCY: the junior spouse joins the senior house (org membership +
    family channel + estate). CUSTOM: recorded prose, socially binding only.
    """

    DOWRY = "dowry", "Dowry"
    SUBSIDY = "subsidy", "Recurring Subsidy"
    CRISIS_RESPONSE = "crisis_response", "Crisis Response"
    RESIDENCY = "residency", "Residency"
    CUSTOM = "custom", "Custom (prose)"


class PactDissolutionReason(models.TextChoices):
    DEATH = "death", "A spouse died"
    ANNULMENT = "annulment", "Annulled"
    BREACH = "breach", "Broken by breach"


class DomainCrisisSeverity(models.TextChoices):
    TROUBLE = "trouble", "Trouble"
    CRISIS = "crisis", "Crisis"
    CATASTROPHE = "catastrophe", "Catastrophe"


class HouseClaimStatus(models.TextChoices):
    """Lifecycle of a CG house-founding claim (#1884 Phase D)."""

    PENDING = "pending", "Pending Review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
