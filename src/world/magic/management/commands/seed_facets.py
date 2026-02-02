"""Management command to seed the facet hierarchy."""

from django.core.management.base import BaseCommand
from django.db import transaction

from world.magic.constants import FACET_HIERARCHY
from world.magic.models import Facet


class Command(BaseCommand):
    """Seed the facet hierarchy (categories, subcategories, specific facets)."""

    help = "Seed the facet hierarchy (categories, subcategories, specific facets)."

    @transaction.atomic
    def handle(self, *_args, **_options):
        created_count = 0
        updated_count = 0

        for category_name, subcategories in FACET_HIERARCHY.items():
            # Create category (top-level)
            category, created = Facet.objects.get_or_create(
                name=category_name,
                parent=None,
            )
            if created:
                created_count += 1
                self.stdout.write(f"Created category: {category_name}")
            else:
                updated_count += 1

            for subcategory_name, facets in subcategories.items():
                # Create subcategory
                subcategory, created = Facet.objects.get_or_create(
                    name=subcategory_name,
                    parent=category,
                )
                if created:
                    created_count += 1
                    self.stdout.write(f"  Created subcategory: {subcategory_name}")
                else:
                    updated_count += 1

                for facet_name in facets:
                    # Create specific facet
                    _, created = Facet.objects.get_or_create(
                        name=facet_name,
                        parent=subcategory,
                    )
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded facets: {created_count} created, {updated_count} already existed"
            )
        )
