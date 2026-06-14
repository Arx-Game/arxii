"""SPREAD_ASSIST reaction kind (#915).

PCs present at a telling (a ``spread_a_tale`` resolution) may *acclaim* it.
Acclaim is tallied at scene close: a minor bonus spread is added to the deed
(a fraction of the original telling's value per acclaim, clamped by the deed's
remaining capacity and an optional per-scene cap), and each acclaiming reactor
earns a little engagement. PC assists are deliberately minor — the NPC traffic
band stays the primary spread vector.

Registered from ``SocietiesConfig.ready()`` so scenes never imports societies.
The window's deed + original value live on a ``SpreadAssistTarget`` (the
per-kind settlement record), written when the telling opens the window.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.scenes.reaction_services import ReactionChoice, ReactionKindConfig

if TYPE_CHECKING:
    from world.progression.models import KudosSourceCategory
    from world.scenes.reaction_models import ReactionWindow, WindowReaction

ACCLAIM_CHOICE = "acclaim"
SPREAD_ASSIST_KUDOS_CATEGORY = "spread_assist"

# PLACEHOLDER player-facing label — rewrite in the project voice.
_CHOICES = [ReactionChoice(slug=ACCLAIM_CHOICE, label="PLACEHOLDER: Acclaim this telling")]


def _spread_assist_choices(window: ReactionWindow) -> list[ReactionChoice]:  # noqa: ARG001
    return _CHOICES


def _on_spread_assist_reaction(window: ReactionWindow, reaction: WindowReaction) -> None:
    """No immediate effect — acclaim is tallied at scene close in on_settle."""


def _get_spread_assist_kudos_category() -> KudosSourceCategory:
    from world.progression.models import KudosSourceCategory  # noqa: PLC0415

    category, _ = KudosSourceCategory.objects.get_or_create(
        name=SPREAD_ASSIST_KUDOS_CATEGORY,
        defaults={
            "display_name": "Telling Acclaim",
            "description": "You acclaimed a tale someone told, helping it spread.",
            "default_amount": 1,
        },
    )
    return category


def _settle_spread_assist(window: ReactionWindow) -> None:
    """At scene close: bonus spread for acclaim + engagement for the acclaimers."""
    from world.progression.services.kudos import award_kudos  # noqa: PLC0415
    from world.societies.models import SpreadAssistTarget, SpreadingConfig  # noqa: PLC0415
    from world.societies.services import spread_deed  # noqa: PLC0415

    target = SpreadAssistTarget.objects.filter(window=window).select_related("legend_entry").first()
    if target is None:
        return

    acclaims = list(
        window.reactions.filter(choice=ACCLAIM_CHOICE).select_related("reactor_persona")
    )
    if not acclaims:
        return

    config = SpreadingConfig.get_active_config()
    bonus = round(target.original_value * config.spread_assist_fraction * len(acclaims))
    cap = config.spread_assist_per_scene_cap
    if cap > 0:
        bonus = min(bonus, cap)

    if bonus > 0:
        # One bonus spread, credited to the teller whose tale the crowd amplified.
        # spread_deed clamps to the deed's remaining capacity.
        spread_deed(
            deed=target.legend_entry,
            spreader_persona=window.interaction.persona,
            value_added=bonus,
            method="spread_assist",
            scene=window.scene,
        )

    category = _get_spread_assist_kudos_category()
    for reaction in acclaims:
        account = reaction.reactor_persona.character_sheet.character.db_account
        if account is None:
            continue
        award_kudos(
            account=account,
            amount=category.default_amount,
            source_category=category,
            description=f"Engagement for acclaiming a telling in {window.scene}",
        )


SPREAD_ASSIST_KIND = ReactionKindConfig(
    choices_for=_spread_assist_choices,
    on_reaction=_on_spread_assist_reaction,
    on_settle=_settle_spread_assist,
    public=True,
    lazy_open=False,
)
