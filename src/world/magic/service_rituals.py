"""The service functions a SERVICE ritual may run, the list staff pick from in the admin.

A SERVICE ``Ritual``'s ``service_function_path`` decides which code runs when it is
performed, so the Ritual admin offers only the paths listed here (a select, refused in the
form's ``clean`` when unknown), never free text: a free path would let anyone with a staff
login point a rite at any function. A new SERVICE rite's function is added here in the PR
that adds the function.

Paths are plain strings so this module imports nothing; ``world/magic/tests`` checks each
one imports to a callable and that the constants the services find their rites by
(``RESWEAR_SERVICE_PATH``, ``THREAD_RESONANCE_SERVICE_PATH`` and the rest) are listed.
"""

from __future__ import annotations

#: path -> the label the admin shows. Ordered by system, then label.
SERVICE_RITUAL_FUNCTIONS: dict[str, str] = {
    # Covenants
    "world.covenants.focus_picks.reswear_vow_pick": "Covenants: Rite of Re-swearing",
    "world.covenants.services.create_covenant_via_session": "Covenants: found a covenant",
    "world.covenants.services.establish_mentor_bond_via_session": (
        "Covenants: establish a mentor bond"
    ),
    "world.covenants.services.induct_member_via_session": "Covenants: induct a member",
    "world.covenants.services.perform_covenant_rite": "Covenants: covenant rite",
    "world.covenants.services.rise_battle_covenant_via_session": (
        "Covenants: raise a battle covenant"
    ),
    # Magic
    "world.magic.services.atonement.perform_atonement_rite": "Magic: atonement",
    "world.magic.services.drift_correction.perform_drift_correction_rite": (
        "Magic: drift correction"
    ),
    "world.magic.services.fall_redemption.perform_fall": "Magic: Ritual of Falling",
    "world.magic.services.ghost_tutor.summon_ghost_tutor": "Magic: summon a ghost tutor",
    "world.magic.services.sanctum_install.perform_dissolution": "Magic: sanctum dissolution",
    "world.magic.services.sanctum_install.perform_sanctification": "Magic: sanctification",
    "world.magic.services.sanctum_rituals.perform_homecoming_ritual": "Magic: homecoming",
    "world.magic.services.sanctum_rituals.perform_purging_ritual": "Magic: Ritual of Purging",
    "world.magic.services.soul_tether.accept_soul_tether_via_session": (
        "Magic: accept a soul tether"
    ),
    "world.magic.services.soul_tether.perform_soul_tether_rescue": "Magic: soul tether rescue",
    "world.magic.services.spend_resonance_for_imbuing": "Magic: imbuing (service variant)",
    "world.magic.services.technique_acquisition.learn_technique_from_ritual": (
        "Magic: learn a technique"
    ),
    "world.magic.services.thread_resonance.change_thread_resonance": "Magic: retune a thread",
    "world.magic.services.touchstones.attune_touchstone": "Magic: attune a touchstone",
    # Progression
    "world.progression.services.advancement.advance_class_level_via_session": (
        "Progression: advance a class level"
    ),
    "world.progression.services.durance_registration.register_durance_via_session": (
        "Progression: register a durance"
    ),
    # Societies
    "world.societies.honors.honor_deed": "Societies: Rite of Honors",
    "world.societies.membership_services.induct_organization_member_via_session": (
        "Societies: induct an organization member"
    ),
}


def is_registered_service(path: str) -> bool:
    """True when ``path`` is a service function a SERVICE ritual may run."""
    return path in SERVICE_RITUAL_FUNCTIONS
