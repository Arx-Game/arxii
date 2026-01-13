"""
Management command to initialize default SpeciesOptions.

Creates SpeciesOption records for all Species-StartingArea combinations
with default values (0 cost, no bonuses). Staff can then customize
individual options via Django admin.

Usage:
    arx manage init_species_options
"""

from django.core.management.base import BaseCommand

from world.character_creation.models import SpeciesOption, StartingArea
from world.character_sheets.models import Species


class Command(BaseCommand):
    help = "Initialize default SpeciesOptions for all Species-Area combinations"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without actually creating",
        )

    def handle(self, *args, **options):  # noqa: ARG002, C901, PLR0912
        dry_run = options["dry_run"]

        species_qs = Species.objects.filter(allowed_in_chargen=True)
        areas_qs = StartingArea.objects.filter(is_active=True)

        species_count = species_qs.count()
        areas_count = areas_qs.count()

        if species_count == 0:
            self.stdout.write(
                self.style.WARNING(
                    "No Species with allowed_in_chargen=True found. Create Species records first."
                )
            )
            return

        if areas_count == 0:
            self.stdout.write(
                self.style.WARNING(
                    "No StartingAreas with is_active=True found. Create StartingArea records first."
                )
            )
            return

        self.stdout.write(f"Found {species_count} species and {areas_count} areas")
        self.stdout.write(f"Will create up to {species_count * areas_count} SpeciesOptions")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN - No changes made\n"))

        created_count = 0
        existing_count = 0

        for species in species_qs:
            for area in areas_qs:
                if dry_run:
                    exists = SpeciesOption.objects.filter(
                        species=species, starting_area=area
                    ).exists()
                    if exists:
                        self.stdout.write(f"  Would skip (exists): {species.name} ({area.name})")
                        existing_count += 1
                    else:
                        self.stdout.write(f"  Would create: {species.name} ({area.name})")
                        created_count += 1
                else:
                    option, created = SpeciesOption.objects.get_or_create(
                        species=species,
                        starting_area=area,
                        defaults={
                            "cg_point_cost": 0,
                            "stat_bonuses": {},
                            "starting_languages": [],
                            "trust_required": 0,
                            "is_available": True,
                            "sort_order": 0,
                        },
                    )
                    if created:
                        self.stdout.write(self.style.SUCCESS(f"  ✓ Created: {option}"))
                        created_count += 1
                    else:
                        self.stdout.write(f"  - Already exists: {option}")
                        existing_count += 1

        self.stdout.write("\n" + "=" * 60)
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"DRY RUN: Would create {created_count}, skip {existing_count}")
            )
        else:
            self.stdout.write(self.style.SUCCESS(f"✓ Created {created_count} new SpeciesOptions"))
            if existing_count > 0:
                self.stdout.write(f"  {existing_count} already existed")
