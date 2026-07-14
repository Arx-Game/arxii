"""Seed ContributionMethod rows for the WAR_FUNDING project kind (#2382).

Three check-based contribution methods, each reusing an existing CheckType:
"Drill Troops" (Household Command), "Scout Enemy Positions" (Stealth),
"Fortify Defenses" (Search). AP cost / progress magnitudes are PLACEHOLDER
(tuning ledger §6), mirroring the BUILDING_PREPARATION seed's values.
"""

from __future__ import annotations


def seed_war_funding_contribution_methods() -> None:
    """Seed three ContributionMethod rows for WAR_FUNDING (#2382).

    Idempotent — uses ``update_or_create`` on (kind, name), so re-runs
    update existing rows and staff edits survive a re-seed. Each method
    references an already-seeded CheckType; the relevant seed function is
    called if the CheckType is missing (mirroring ``buildings/seeds.py``).
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.projects.constants import ProjectKind  # noqa: PLC0415
    from world.projects.models import ContributionMethod  # noqa: PLC0415
    from world.seeds.governance_checks import seed_governance_check_content  # noqa: PLC0415
    from world.seeds.investigation_checks import seed_investigation_check_content  # noqa: PLC0415
    from world.seeds.stealth_checks import seed_stealth_check_content  # noqa: PLC0415

    def _get_check_type(name: str, seeder: object) -> CheckType:
        ct = CheckType.objects.filter(name=name).first()
        if ct is None:
            seeder()
            ct = CheckType.objects.get(name=name)
        return ct

    methods = [
        (
            "Drill Troops",
            "Household Command",
            seed_governance_check_content,
            "PLACEHOLDER — rally and drill troops to improve military readiness.",
        ),
        (
            "Scout Enemy Positions",
            "Stealth",
            seed_stealth_check_content,
            "PLACEHOLDER — scout enemy positions to gather intelligence for the war effort.",
        ),
        (
            "Fortify Defenses",
            "Search",
            seed_investigation_check_content,
            "PLACEHOLDER — survey and fortify defensive positions.",
        ),
    ]

    for method_name, check_type_name, seeder, description in methods:
        check_type = _get_check_type(check_type_name, seeder)
        ContributionMethod.objects.update_or_create(
            kind=ProjectKind.WAR_FUNDING,
            name=method_name,
            defaults={
                "description": description,
                "check_type": check_type,
                "ap_cost": 5,
                "progress_on_success": 10,
            },
        )
