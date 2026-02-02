"""Management command to seed the 24 resonances."""

from django.core.management.base import BaseCommand
from django.db import transaction

from world.magic.constants import (
    ABYSSAL_RESONANCES,
    CELESTIAL_ABYSSAL_PAIRS,
    CELESTIAL_RESONANCES,
    PRIMAL_PAIRS,
    PRIMAL_RESONANCES,
)
from world.mechanics.constants import ResonanceAffinity
from world.mechanics.models import ModifierCategory, ModifierType


class Command(BaseCommand):
    """Seed the 24 resonances with their opposites and affinities."""

    help = "Seed the 24 resonances with their opposites and affinities."

    @transaction.atomic
    def handle(self, *_args, **_options):
        # Get or create resonance category
        category, _ = ModifierCategory.objects.get_or_create(
            name="resonance",
            defaults={"description": "Resonance types for magic system"},
        )

        # Create Celestial resonances
        self.stdout.write("Creating Celestial resonances...")
        celestial_map = {}
        for name, description in CELESTIAL_RESONANCES:
            res, created = ModifierType.objects.update_or_create(
                name=name,
                category=category,
                defaults={
                    "description": description,
                    "resonance_affinity": ResonanceAffinity.CELESTIAL,
                },
            )
            celestial_map[name] = res
            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status}: {name}")

        # Create Abyssal resonances
        self.stdout.write("Creating Abyssal resonances...")
        abyssal_map = {}
        for name, description in ABYSSAL_RESONANCES:
            res, created = ModifierType.objects.update_or_create(
                name=name,
                category=category,
                defaults={
                    "description": description,
                    "resonance_affinity": ResonanceAffinity.ABYSSAL,
                },
            )
            abyssal_map[name] = res
            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status}: {name}")

        # Create Primal resonances
        self.stdout.write("Creating Primal resonances...")
        primal_map = {}
        for name, description in PRIMAL_RESONANCES:
            res, created = ModifierType.objects.update_or_create(
                name=name,
                category=category,
                defaults={
                    "description": description,
                    "resonance_affinity": ResonanceAffinity.PRIMAL,
                },
            )
            primal_map[name] = res
            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status}: {name}")

        # Link Celestial-Abyssal pairs
        self.stdout.write("Linking Celestial-Abyssal pairs...")
        for celestial_name, abyssal_name in CELESTIAL_ABYSSAL_PAIRS:
            celestial = celestial_map[celestial_name]
            abyssal = abyssal_map[abyssal_name]
            celestial.opposite = abyssal
            abyssal.opposite = celestial
            celestial.save()
            abyssal.save()
            self.stdout.write(f"  Linked: {celestial_name} <-> {abyssal_name}")

        # Link Primal pairs
        self.stdout.write("Linking Primal pairs...")
        for primal_a, primal_b in PRIMAL_PAIRS:
            a = primal_map[primal_a]
            b = primal_map[primal_b]
            a.opposite = b
            b.opposite = a
            a.save()
            b.save()
            self.stdout.write(f"  Linked: {primal_a} <-> {primal_b}")

        self.stdout.write(self.style.SUCCESS("Successfully seeded 24 resonances!"))
