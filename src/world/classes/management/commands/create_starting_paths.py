"""Management command to create starting paths."""

from django.core.management.base import BaseCommand

from world.classes.models import Aspect, Path, PathAspect, PathStage


class Command(BaseCommand):
    help = "Create the 5 starting paths and their aspects"

    def handle(self, *args, **options):  # noqa: ARG002
        # Create aspects
        aspects = {}
        aspect_data = [
            ("Warfare", "Combat and martial prowess"),
            ("Martial", "Physical discipline and training"),
            ("Subterfuge", "Deception, stealth, and misdirection"),
            ("Shadow", "Operating unseen and unheard"),
            ("Diplomacy", "Negotiation and social maneuvering"),
            ("Performance", "Artistic expression and entertainment"),
            ("Devotion", "Dedication to higher powers or ideals"),
            ("Faith", "Spiritual connection and belief"),
            ("Scholarship", "Academic study and research"),
            ("Arcana", "Understanding of magical theory"),
        ]
        for name, desc in aspect_data:
            aspects[name], _ = Aspect.objects.get_or_create(
                name=name, defaults={"description": desc}
            )
            self.stdout.write(f"  Aspect: {name}")

        # Create starting paths
        paths_data = [
            {
                "name": "Path of Steel",
                "description": (
                    "The martial path of warriors, soldiers, and those who live by "
                    "the blade. Steel practitioners master combat, defense, and "
                    "physical prowess."
                ),
                "aspects": [("Warfare", 2), ("Martial", 1)],
            },
            {
                "name": "Path of Whispers",
                "description": (
                    "The shadowed path of rogues, spies, and those who move unseen. "
                    "Whisper practitioners excel at stealth, subterfuge, and striking "
                    "from darkness."
                ),
                "aspects": [("Subterfuge", 2), ("Shadow", 1)],
            },
            {
                "name": "Path of the Voice",
                "description": (
                    "The social path of courtiers, diplomats, and performers. Voice "
                    "practitioners master persuasion, presence, and the art of "
                    "influence."
                ),
                "aspects": [("Diplomacy", 2), ("Performance", 1)],
            },
            {
                "name": "Path of the Chosen",
                "description": (
                    "The devoted path of acolytes, priests, and those sworn to higher "
                    "powers. Chosen practitioners channel faith and serve ideals "
                    "greater than themselves."
                ),
                "aspects": [("Devotion", 2), ("Faith", 1)],
            },
            {
                "name": "Path of the Tome",
                "description": (
                    "The scholarly path of academics, sages, and seekers of knowledge. "
                    "Tome practitioners pursue understanding of the world's mysteries "
                    "and magical arts."
                ),
                "aspects": [("Scholarship", 2), ("Arcana", 1)],
            },
        ]

        for path_data in paths_data:
            path, created = Path.objects.get_or_create(
                name=path_data["name"],
                defaults={
                    "description": path_data["description"],
                    "stage": PathStage.QUIESCENT,
                    "minimum_level": 1,
                },
            )
            action = "Created" if created else "Found"
            self.stdout.write(f"{action} path: {path.name}")

            # Add aspects (using character_path due to SharedMemoryModel constraint)
            for aspect_name, weight in path_data["aspects"]:
                PathAspect.objects.get_or_create(
                    character_path=path,
                    aspect=aspects[aspect_name],
                    defaults={"weight": weight},
                )

        self.stdout.write(self.style.SUCCESS("Starting paths created successfully"))
