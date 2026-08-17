"""Predator ecology services (#3093): the slow menace ladder.

A band fixates on the weakest-perceived landed org in reach and climbs one
small stage at a time — only while unanswered. Roughly ten weekly crons
separate the first rumor from an actual raid, and every transition emits a
MenaceEvent the tidings read, so players always see it coming. Counterplay
(a resolved raid, sabotage, a hunt) knocks the ladder down and burns
strength; mauled bands go dormant, broken ones disband.

Afflictions ride the same app: deterrence-blind outbreaks announced by a
week of SIGNS, spreading slowly while ignored.
"""

from __future__ import annotations

from datetime import timedelta
import random
from typing import TYPE_CHECKING

from django.db import models
from django.utils import timezone

from world.predators.constants import (
    _STAGE_ORDER,
    AFFLICTION_SIGN_PCT,
    AFFLICTION_SPREAD_MAX,
    AFFLICTION_SPREAD_PCT,
    BAND_SPAWN_PCT,
    DORMANCY_FLOOR,
    DORMANCY_WEEKS,
    LAWLESSNESS_UNREST_TICK,
    RAID_SEVERITY_BY_STAGE,
    ROBBERY_SKIM_PCT,
    SABOTAGE_STRENGTH_BURN,
    STAGE_WEEKS,
    STRIKE_STRENGTH_BURN,
    MenaceStage,
)
from world.predators.models import AfflictionSign, MenaceEvent, PredatorBand, PredatorKind

if TYPE_CHECKING:
    from world.societies.models import Organization

# PLACEHOLDER feed lines per stage, pending the content pass.
_STAGE_HEADLINES: dict[str, str] = {
    MenaceStage.RUMORS: "PLACEHOLDER Rumors of {band} stir near {region}.",
    MenaceStage.LAWLESSNESS: "PLACEHOLDER Petty crime spreads where {band} rides.",
    MenaceStage.ROBBERY: "PLACEHOLDER {band} robs the roads; coffers bleed.",
    MenaceStage.RAIDS: "PLACEHOLDER {band} raids in force.",
    MenaceStage.TERROR: "PLACEHOLDER {band} puts the countryside to terror.",
}
_KNOCKDOWN_HEADLINE = "PLACEHOLDER {band} reels from a blow and falls back."
_DISBAND_HEADLINE = "PLACEHOLDER {band} is broken and scattered."


def _record_event(band: PredatorBand, *, escalated: bool, headline: str | None = None) -> None:
    region = band.home_region.name if band.home_region_id else ""
    text = (headline or _STAGE_HEADLINES.get(band.stage, "{band}")).format(
        band=band.name, region=region
    )
    MenaceEvent.objects.create(band=band, stage=band.stage, escalated=escalated, headline=text)


def has_regional_peace(org: Organization, band: PredatorBand) -> bool:
    """Consort-derived regional peace (#3091 ruling): a house whose family holds
    an active consort-kind union of the band's home realm is off the menu."""
    from world.roster.models import Union  # noqa: PLC0415

    realm_id = band.home_region.realm_id if band.home_region_id else None
    if realm_id is None or org.family_id is None:
        return False
    return Union.objects.filter(
        members__family_memberships__family_id=org.family_id,
        members__family_memberships__ended_at__isnull=True,
        ended_at__isnull=True,
        kind__realm_id=realm_id,
        kind__requires_landed_title=True,
        kind__stature_share_pct__gt=0,
    ).exists()


def select_prey(band: PredatorBand) -> Organization | None:
    """The weakest-PERCEIVED landed org in reach, honoring regional peace.

    Reach v1: orgs whose domains sit in the band's home realm; when the realm
    holds none (or areas carry no realm), any landed org qualifies — a hungry
    band travels.
    """
    from world.societies.houses.models import HouseStature  # noqa: PLC0415
    from world.societies.houses.stature_services import landed_orgs  # noqa: PLC0415

    realm_id = band.home_region.realm_id if band.home_region_id else None
    candidates = landed_orgs()
    if realm_id is not None:
        in_realm = candidates.filter(domains__area__realm_id=realm_id).distinct()
        if in_realm.exists():
            candidates = in_realm
    rows = (
        HouseStature.objects.filter(organization__in=candidates)
        .select_related("organization")
        .order_by("perceived_total", "organization_id")
    )
    for row in rows:
        if not has_regional_peace(row.organization, band):
            return row.organization
    fallback = candidates.exclude(stature__isnull=False).order_by("pk").first()
    if fallback is not None and not has_regional_peace(fallback, band):
        return fallback
    return None


def _stage_index(stage: str) -> int:
    return _STAGE_ORDER.index(stage)


def _weeks_needed(band: PredatorBand) -> int | None:
    """Weeks unanswered required to advance; None at the ladder's top."""
    if band.stage == MenaceStage.TERROR:
        return None
    override = band.kind.weeks_per_stage_override
    return override if override is not None else STAGE_WEEKS[band.stage]


def _advance(band: PredatorBand) -> None:
    band.stage = _STAGE_ORDER[_stage_index(band.stage) + 1]
    band.weeks_unanswered = 0
    band.stage_entered_at = timezone.now()
    band.save(update_fields=["stage", "weeks_unanswered", "stage_entered_at"])
    _record_event(band, escalated=True)


def _apply_lawlessness(band: PredatorBand) -> None:
    from world.societies.houses.models import Domain  # noqa: PLC0415

    for domain in Domain.objects.filter(owner_org=band.prey):
        new_unrest = min(100, domain.unrest + LAWLESSNESS_UNREST_TICK)
        if new_unrest != domain.unrest:
            domain.unrest = new_unrest
            domain.save(update_fields=["unrest"])


def _apply_robbery(band: PredatorBand) -> None:
    """Skim the prey's uncollected pools into the band's stash."""
    from world.currency.models import OrgIncomeStream  # noqa: PLC0415

    skimmed = 0
    for stream in OrgIncomeStream.objects.filter(organization=band.prey, active=True):
        cut = stream.uncollected_pool * ROBBERY_SKIM_PCT // 100
        if cut <= 0:
            continue
        stream.uncollected_pool -= cut
        stream.save(update_fields=["uncollected_pool"])
        skimmed += cut
    if skimmed:
        band.loot_stash += skimmed
        band.save(update_fields=["loot_stash"])


def _ensure_raid_crisis(band: PredatorBand, *, rng: random.Random) -> None:
    """RAIDS+: keep one open attributed crisis on the prey's weakest domain."""
    from world.societies.houses.constants import CrisisAudience, CrisisOrigin  # noqa: PLC0415
    from world.societies.houses.crisis_services import (  # noqa: PLC0415
        open_crisis,
        pick_crisis_type,
    )
    from world.societies.houses.models import Domain  # noqa: PLC0415

    if band.authored_crises.filter(resolved_at__isnull=True).exists():
        return
    domain = Domain.objects.filter(owner_org=band.prey).order_by("prosperity").first()
    if domain is None:
        return
    crisis_type = pick_crisis_type(
        CrisisOrigin.PREDATOR, audiences=[CrisisAudience.DOMAIN], rng=rng
    )
    crisis = open_crisis(domain, origin=CrisisOrigin.PREDATOR, crisis_type=crisis_type, rng=rng)
    if crisis is None:
        return
    crisis.aggressor_band = band
    # After two months of public menace there is no covert window on a raid —
    # the whole region has watched this band climb the ladder.
    crisis.surfaces_at = None
    severity = RAID_SEVERITY_BY_STAGE.get(band.stage)
    if severity:
        crisis.severity = severity
    crisis.save(update_fields=["aggressor_band", "surfaces_at", "severity"])


def strike_band(
    band: PredatorBand, *, strength_burn: int = STRIKE_STRENGTH_BURN, stages: int = 1
) -> PredatorBand:
    """Counterplay landed: burn strength, knock the ladder down, maybe break them."""
    band.strength = max(0, band.strength - strength_burn)
    band.weeks_unanswered = 0
    if band.strength == 0:
        band.disbanded_at = timezone.now()
        band.save(update_fields=["strength", "weeks_unanswered", "disbanded_at"])
        _record_event(band, escalated=False, headline=_DISBAND_HEADLINE)
        return band
    new_index = max(0, _stage_index(band.stage) - stages)
    band.stage = _STAGE_ORDER[new_index]
    band.stage_entered_at = timezone.now()
    if band.strength < DORMANCY_FLOOR:
        band.dormant_until = timezone.now() + timedelta(weeks=DORMANCY_WEEKS)
    band.save(
        update_fields=[
            "strength",
            "weeks_unanswered",
            "stage",
            "stage_entered_at",
            "dormant_until",
        ]
    )
    _record_event(band, escalated=False, headline=_KNOCKDOWN_HEADLINE)
    return band


def sabotage_band(band: PredatorBand) -> PredatorBand:
    """The spy payout's knife in the dark — smaller burn, same ladder knockdown."""
    return strike_band(band, strength_burn=SABOTAGE_STRENGTH_BURN, stages=1)


def _maybe_spawn_band(*, rng: random.Random) -> PredatorBand | None:
    """Realms without an active band roll a small weekly chance of growing one."""
    from world.areas.models import Area  # noqa: PLC0415
    from world.realms.models import Realm  # noqa: PLC0415

    kinds = list(PredatorKind.objects.all())
    if not kinds:
        return None
    menaced_realm_ids = {
        band.home_region.realm_id
        for band in PredatorBand.objects.filter(disbanded_at__isnull=True).select_related(
            "home_region"
        )
        if band.home_region.realm_id is not None
    }
    for realm in Realm.objects.exclude(pk__in=menaced_realm_ids):
        if rng.random() * 100 >= BAND_SPAWN_PCT:
            continue
        anchor = Area.objects.filter(realm=realm).order_by("pk").first()
        if anchor is None:
            continue
        kind = rng.choice(kinds)
        band = PredatorBand.objects.create(
            name=f"PLACEHOLDER {kind.name} of {realm.name}",
            kind=kind,
            home_region=anchor,
            strength=kind.base_strength,
        )
        _record_event(band, escalated=True)
        return band
    return None


def _tick_band_menace(band: PredatorBand, *, rng: random.Random) -> tuple[bool, bool]:
    """Advance one active band's weekly stalk/pressure/escalate cycle.

    Returns ``(pressured, advanced)``. An inactive band, or one with no reachable
    prey, is skipped and returns ``(False, False)`` — mirrors the original loop's
    early ``continue``.
    """
    if not band.is_active:
        return False, False
    if band.prey is None or has_regional_peace(band.prey, band):
        band.prey = select_prey(band)
        band.save(update_fields=["prey"])
    if band.prey is None:
        return False, False
    stage_idx = _stage_index(band.stage)
    pressured = False
    if stage_idx >= _stage_index(MenaceStage.LAWLESSNESS):
        _apply_lawlessness(band)
        pressured = True
    if stage_idx >= _stage_index(MenaceStage.ROBBERY):
        _apply_robbery(band)
    if stage_idx >= _stage_index(MenaceStage.RAIDS):
        _ensure_raid_crisis(band, rng=rng)
    band.weeks_unanswered += 1
    band.save(update_fields=["weeks_unanswered"])
    needed = _weeks_needed(band)
    advanced = False
    if needed is not None and band.weeks_unanswered >= needed:
        _advance(band)
        advanced = True
    return pressured, advanced


def weekly_menace_tick(*, rng: random.Random | None = None) -> dict[str, int]:
    """The weekly heartbeat: spawn, stalk, pressure, and (slowly) escalate."""
    rng = rng or random
    spawned = 1 if _maybe_spawn_band(rng=rng) is not None else 0
    advanced = 0
    pressured = 0
    for band in PredatorBand.objects.filter(disbanded_at__isnull=True).select_related(
        "kind", "home_region", "prey"
    ):
        band_pressured, band_advanced = _tick_band_menace(band, rng=rng)
        if band_pressured:
            pressured += 1
        if band_advanced:
            advanced += 1
    return {"spawned": spawned, "advanced": advanced, "pressured": pressured}


# ---------------------------------------------------------------------------
# Afflictions (#3093): deterrence-blind, sign-announced, slow-spreading
# ---------------------------------------------------------------------------


def _affliction_types():
    from world.societies.houses.models import DomainCrisisType  # noqa: PLC0415

    return DomainCrisisType.objects.filter(ignores_stature=True, automated=True)


def _convert_due_signs() -> int:
    """Last week's dread becomes this week's outbreak — always announced first."""
    from world.societies.houses.constants import CrisisOrigin  # noqa: PLC0415
    from world.societies.houses.crisis_services import open_crisis  # noqa: PLC0415

    converted = 0
    for sign in AfflictionSign.objects.filter(converted_at__isnull=True).select_related(
        "domain", "crisis_type"
    ):
        crisis = open_crisis(
            sign.domain, origin=CrisisOrigin.AFFLICTION, crisis_type=sign.crisis_type
        )
        sign.converted_at = timezone.now()
        sign.save(update_fields=["converted_at"])
        if crisis is not None:
            converted += 1
    return converted


def _maybe_mint_sign(*, rng: random.Random) -> int:
    """A small, band-blind weekly chance of SIGNS somewhere — never a raw outbreak."""
    from world.societies.houses.models import Domain  # noqa: PLC0415

    types = list(_affliction_types())
    if not types:
        return 0
    minted = 0
    if rng.random() * 100 < AFFLICTION_SIGN_PCT:
        domains = list(
            Domain.objects.exclude(affliction_signs__converted_at__isnull=True).order_by("pk")
        )
        if not domains:
            domains = list(Domain.objects.order_by("pk"))
        if domains:
            AfflictionSign.objects.create(domain=rng.choice(domains), crisis_type=rng.choice(types))
            minted = 1
    return minted


def _spread_afflictions(*, rng: random.Random) -> int:
    """Unresolved spreading outbreaks jump one domain per week, capped per root."""
    from world.societies.houses.constants import CrisisOrigin  # noqa: PLC0415
    from world.societies.houses.crisis_services import open_crisis  # noqa: PLC0415
    from world.societies.houses.models import Domain, DomainCrisis  # noqa: PLC0415

    spread = 0
    roots = DomainCrisis.objects.filter(
        resolved_at__isnull=True,
        crisis_type__affliction_spreads=True,
        spread_count__lt=AFFLICTION_SPREAD_MAX,
        domain__isnull=False,
    ).select_related("domain__area", "crisis_type")
    for root in roots:
        if rng.random() * 100 >= AFFLICTION_SPREAD_PCT:
            continue
        realm_id = root.domain.area.realm_id
        neighbors = Domain.objects.exclude(pk=root.domain_id)
        if realm_id is not None:
            neighbors = neighbors.filter(area__realm_id=realm_id)
        neighbor = (
            neighbors.exclude(
                crises__resolved_at__isnull=True, crises__crisis_type=root.crisis_type
            )
            .order_by("pk")
            .first()
        )
        if neighbor is None:
            continue
        sibling = open_crisis(
            neighbor, origin=CrisisOrigin.AFFLICTION, crisis_type=root.crisis_type
        )
        if sibling is None:
            continue
        root.spread_count = models.F("spread_count") + 1
        root.save(update_fields=["spread_count"])
        root.refresh_from_db(fields=["spread_count"])
        spread += 1
    return spread


def weekly_affliction_tick(*, rng: random.Random | None = None) -> dict[str, int]:
    rng = rng or random
    converted = _convert_due_signs()
    minted = _maybe_mint_sign(rng=rng)
    spread = _spread_afflictions(rng=rng)
    return {"signs": minted, "outbreaks": converted, "spread": spread}
