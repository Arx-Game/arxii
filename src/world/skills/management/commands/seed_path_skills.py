"""
Management command to seed path skill suggestion data.

Creates the suggested skill allocations for each path (50 points each).
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from world.classes.models import Path
from world.skills.models import PathSkillSuggestion, Skill

# Path skill suggestions: (path_name, [(skill_name, value), ...])
# Each path gets 50 points total to allocate
PATH_SKILL_DATA = {
    "Path of Steel": [
        # Martial path - combat focused
        ("Melee Combat", 30),  # 30 pts - primary combat skill
        ("Defense", 10),  # 10 pts - blocking/dodging
        ("Athletics", 10),  # 10 pts - physical prowess
    ],
    "Path of Whispers": [
        # Shadowed path - stealth and subterfuge
        ("Stealth", 20),  # 20 pts - primary skill
        ("Melee Combat", 10),  # 10 pts - dagger work
        ("Investigation", 10),  # 10 pts - gathering intel
        ("Survival", 10),  # 10 pts - operating in wilderness
    ],
    "Path of the Voice": [
        # Social path - influence and presence
        ("Persuasion", 30),  # 30 pts - primary social skill
        ("Performance", 10),  # 10 pts - entertaining
        ("Investigation", 10),  # 10 pts - carousing for information
    ],
    "Path of the Chosen": [
        # Devoted path - faith and divine magic
        ("Ritual Magic", 20),  # 20 pts - divine ceremonies
        ("Occult", 20),  # 20 pts - spiritual knowledge
        ("Medicine", 10),  # 10 pts - healing the faithful
    ],
    "Path of the Tome": [
        # Scholarly path - knowledge and arcane study
        ("Scholarship", 20),  # 20 pts - academic knowledge
        ("Occult", 20),  # 20 pts - magical theory
        ("Investigation", 10),  # 10 pts - research
    ],
}


class Command(BaseCommand):
    help = "Seed path skill suggestion data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Delete existing path skill suggestions and recreate",
        )

    def handle(self, **options):
        force = options["force"]
        expected_points = 50

        if force:
            self.stdout.write("Deleting existing path skill suggestions...")
            PathSkillSuggestion.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("Existing suggestions deleted."))

        existing_count = PathSkillSuggestion.objects.count()
        if existing_count > 0 and not force:
            msg = (
                f"Path skill suggestions already exist ({existing_count}). Use --force to recreate."
            )
            raise CommandError(msg)

        # Validate all paths and skills exist
        for path_name, skill_list in PATH_SKILL_DATA.items():
            try:
                Path.objects.get(name=path_name)
            except Path.DoesNotExist as e:
                msg = f"Path '{path_name}' not found in database."
                raise CommandError(msg) from e

            total_points = 0
            for skill_name, value in skill_list:
                try:
                    Skill.objects.get(trait__name=skill_name)
                except Skill.DoesNotExist as e:
                    msg = f"Skill '{skill_name}' not found for path '{path_name}'."
                    raise CommandError(msg) from e
                total_points += value

            if total_points != expected_points:
                self.stdout.write(
                    self.style.WARNING(
                        f"Path '{path_name}' allocates {total_points} points (expected 50)"
                    )
                )

        with transaction.atomic():
            suggestions_created = 0

            for path_name, skill_list in PATH_SKILL_DATA.items():
                path = Path.objects.get(name=path_name)
                self.stdout.write(f"\n{path_name}:")

                for order, (skill_name, value) in enumerate(skill_list, start=1):
                    skill = Skill.objects.get(trait__name=skill_name)
                    PathSkillSuggestion.objects.create(
                        character_path=path,
                        skill=skill,
                        suggested_value=value,
                        display_order=order * 10,
                    )
                    suggestions_created += 1
                    self.stdout.write(f"  - {skill_name}: {value}")

            self.stdout.write(
                self.style.SUCCESS(f"\nCreated {suggestions_created} path skill suggestions.")
            )
