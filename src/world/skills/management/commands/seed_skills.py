"""
Management command to seed initial skill data.

Creates the 15 parent skills and their specializations based on the design doc.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from world.skills.models import Skill, Specialization
from world.traits.models import Trait, TraitCategory, TraitType

# Skills data structure: (name, category, description, tooltip, [specializations])
SKILLS_DATA = [
    # Combat skills
    (
        "Melee Combat",
        TraitCategory.COMBAT,
        "Close-quarters fighting with weapons or unarmed",
        "Fighting with melee weapons or bare hands",
        [
            ("Swords", "Fighting with bladed swords and similar weapons"),
            ("Unarmed", "Fighting without weapons, including grappling"),
            ("Polearms", "Fighting with spears, halberds, and other polearms"),
            ("Daggers", "Fighting with knives, daggers, and short blades"),
            ("Axes", "Fighting with axes and similar chopping weapons"),
            ("Maces", "Fighting with maces, hammers, and blunt weapons"),
        ],
    ),
    (
        "Ranged Combat",
        TraitCategory.COMBAT,
        "Fighting with projectile weapons",
        "Fighting with bows, crossbows, and thrown weapons",
        [
            ("Archery", "Using bows and longbows"),
            ("Crossbows", "Using crossbows and similar mechanical bows"),
            ("Thrown Weapons", "Throwing knives, axes, and other weapons"),
        ],
    ),
    (
        "Defense",
        TraitCategory.COMBAT,
        "Protecting oneself from attacks",
        "Avoiding or blocking incoming attacks",
        [
            ("Dodge", "Evading attacks through agility"),
            ("Parry", "Deflecting attacks with weapons"),
            ("Shields", "Blocking attacks with shields"),
            ("Magical Defense", "Resisting magical attacks"),
        ],
    ),
    # Social skills
    (
        "Persuasion",
        TraitCategory.SOCIAL,
        "Influencing others through words and presence",
        "Convincing, manipulating, or intimidating others",
        [
            ("Seduction", "Using charm and attraction to influence"),
            ("Intimidation", "Using fear and threat to influence"),
            ("Manipulation", "Subtle psychological influence"),
            ("Empathy", "Understanding and connecting with emotions"),
            ("Negotiation", "Formal bargaining and deal-making"),
        ],
    ),
    (
        "Performance",
        TraitCategory.SOCIAL,
        "Entertaining and captivating audiences",
        "Artistic expression through various media",
        [
            ("Singing", "Vocal performance and music"),
            ("Acting", "Theatrical and dramatic performance"),
            ("Instruments", "Playing musical instruments"),
            ("Oration", "Formal speaking and speeches"),
            ("Dance", "Expressive movement and choreography"),
        ],
    ),
    (
        "Fashion",
        TraitCategory.SOCIAL,
        "Style, presentation, and aesthetic influence",
        "Creating and understanding fashionable presentation",
        [
            ("Modeling", "Presenting clothing and accessories"),
            ("Couture Design", "Creating high-end clothing"),
            ("Magical Attunement", "Fashion with magical properties"),
            ("Costume", "Theatrical and functional costume design"),
        ],
    ),
    # Physical skills
    (
        "Athletics",
        TraitCategory.PHYSICAL,
        "Physical prowess and movement",
        "Running, climbing, swimming, and physical feats",
        [
            ("Climbing", "Scaling walls, cliffs, and structures"),
            ("Running", "Speed and endurance in movement"),
            ("Swimming", "Moving through water"),
            ("Jumping", "Leaping and acrobatic movement"),
        ],
    ),
    (
        "Stealth",
        TraitCategory.PHYSICAL,
        "Moving unseen and unheard",
        "Hiding, sneaking, and covert operations",
        [
            ("Hiding", "Concealing oneself from detection"),
            ("Pickpocketing", "Stealing from others unnoticed"),
            ("Disguise", "Altering appearance to avoid recognition"),
            ("Shadowing", "Following others without detection"),
        ],
    ),
    (
        "Survival",
        TraitCategory.PHYSICAL,
        "Thriving in harsh environments",
        "Living off the land and enduring conditions",
        [
            ("Hunting", "Tracking and killing game for food"),
            ("Fishing", "Catching fish and aquatic creatures"),
            ("Arctic", "Surviving in cold environments"),
            ("Desert", "Surviving in hot, arid environments"),
            ("Foraging", "Finding edible plants and resources"),
        ],
    ),
    # Mental skills
    (
        "Investigation",
        TraitCategory.MENTAL,
        "Discovering hidden information",
        "Research, interrogation, and gathering intelligence",
        [
            ("Research", "Finding information through study"),
            ("Carousing", "Gathering gossip and rumors socially"),
            ("Interrogation", "Extracting information through questioning"),
            ("Tracking", "Following trails and signs"),
        ],
    ),
    (
        "Scholarship",
        TraitCategory.MENTAL,
        "Academic and theoretical knowledge",
        "Understanding complex subjects through study",
        [
            ("Economics", "Understanding trade, markets, and finance"),
            ("Languages", "Learning and translating languages"),
            ("History", "Knowledge of past events and civilizations"),
            ("Sciences", "Understanding natural phenomena"),
            ("Law", "Knowledge of legal systems and procedures"),
        ],
    ),
    (
        "Medicine",
        TraitCategory.MENTAL,
        "Healing and medical knowledge",
        "Treating injuries, diseases, and ailments",
        [
            ("Surgery", "Invasive medical procedures"),
            ("Herbalism", "Using plants for healing"),
            ("Diagnosis", "Identifying medical conditions"),
            ("Poison Treatment", "Treating and understanding poisons"),
        ],
    ),
    (
        "Occult",
        TraitCategory.MENTAL,
        "Knowledge of supernatural phenomena",
        "Understanding magic, spirits, and the arcane",
        [
            ("Demons", "Knowledge of demonic entities"),
            ("Spirits", "Knowledge of ghosts and incorporeal beings"),
            ("Magical Theory", "Understanding how magic works"),
            ("Wards", "Creating and understanding protective barriers"),
        ],
    ),
    # Magic skills
    (
        "Ritual Magic",
        TraitCategory.MAGIC,
        "Performing structured magical ceremonies",
        "Casting spells through ritual and preparation",
        [
            ("Summoning", "Calling forth entities"),
            ("Enchantment", "Imbuing objects with magic"),
            ("Divination", "Seeing the future or hidden things"),
            ("Warding", "Creating magical protections"),
        ],
    ),
    # Crafting skills
    (
        "Artisan",
        TraitCategory.CRAFTING,
        "Creating objects through skilled craftsmanship",
        "Making things with hands and tools",
        [
            ("Blacksmithing", "Forging metal items"),
            ("Tailoring", "Creating and repairing clothing"),
            ("Alchemy", "Creating potions and substances"),
            ("Jewelcrafting", "Creating jewelry and fine items"),
            ("Leatherworking", "Working with leather and hides"),
            ("Carpentry", "Working with wood"),
        ],
    ),
    # War skills
    (
        "War",
        TraitCategory.WAR,
        "Large-scale military operations",
        "Strategy, tactics, and command",
        [
            ("Leadership", "Inspiring and directing troops"),
            ("Tactics", "Small unit and battlefield tactics"),
            ("Siege Warfare", "Attacking and defending fortifications"),
            ("Naval Combat", "Commanding ships and naval forces"),
            ("Logistics", "Supply chains and army management"),
        ],
    ),
]


class Command(BaseCommand):
    help = "Seed initial skill and specialization data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Delete existing skills and recreate",
        )

    def handle(self, **options):
        force = options["force"]

        if force:
            self.stdout.write("Deleting existing skills...")
            Specialization.objects.all().delete()
            Skill.objects.all().delete()
            # Also delete related traits
            Trait.objects.filter(trait_type=TraitType.SKILL).delete()
            self.stdout.write(self.style.SUCCESS("Existing skills deleted."))

        existing_count = Skill.objects.count()
        if existing_count > 0 and not force:
            msg = f"Skills already exist ({existing_count}). Use --force to recreate."
            raise CommandError(msg)

        with transaction.atomic():
            skills_created = 0
            specs_created = 0

            for order, skill_data in enumerate(SKILLS_DATA, start=1):
                name, category, description, tooltip, specializations = skill_data

                # Create the trait first
                trait = Trait.objects.create(
                    name=name,
                    trait_type=TraitType.SKILL,
                    category=category,
                    description=description,
                )

                # Create the skill
                skill = Skill.objects.create(
                    trait=trait,
                    tooltip=tooltip,
                    display_order=order * 10,
                    is_active=True,
                )
                skills_created += 1
                self.stdout.write(f"  Created skill: {name}")

                # Create specializations
                for spec_order, (spec_name, spec_tooltip) in enumerate(specializations, start=1):
                    Specialization.objects.create(
                        name=spec_name,
                        parent_skill=skill,
                        tooltip=spec_tooltip,
                        display_order=spec_order * 10,
                        is_active=True,
                    )
                    specs_created += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"\nCreated {skills_created} skills with {specs_created} specializations."
                )
            )
