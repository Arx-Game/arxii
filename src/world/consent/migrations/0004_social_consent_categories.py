# Generated manually for #1141: data-driven social consent categories

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("consent", "0003_socialconsentpreference_socialconsentwhitelist"),
    ]

    operations = [
        # 1. Create SocialConsentCategory
        migrations.CreateModel(
            name="SocialConsentCategory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "key",
                    models.SlugField(
                        unique=True,
                        help_text="Stable slug (e.g. 'romantic', 'hostile').",
                    ),
                ),
                (
                    "name",
                    models.CharField(max_length=100, help_text="Player-facing label."),
                ),
                (
                    "description",
                    models.TextField(blank=True, help_text="What this category covers."),
                ),
                (
                    "display_order",
                    models.PositiveIntegerField(
                        default=0, help_text="Sort order in the consent UI."
                    ),
                ),
            ],
            options={
                "verbose_name": "Social Consent Category",
                "verbose_name_plural": "Social Consent Categories",
                "ordering": ["display_order", "name"],
            },
        ),
        # 2. Remove require_whitelist from SocialConsentPreference
        migrations.RemoveField(
            model_name="socialconsentpreference",
            name="require_whitelist",
        ),
        # 3. Create SocialConsentCategoryRule
        migrations.CreateModel(
            name="SocialConsentCategoryRule",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "mode",
                    models.CharField(
                        max_length=20,
                        choices=[("everyone", "Everyone"), ("allowlist", "Allowlist only")],
                        default="everyone",
                        help_text="EVERYONE (anyone) or ALLOWLIST (only whitelisted actors).",
                    ),
                ),
                (
                    "preference",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="category_rules",
                        to="consent.socialconsentpreference",
                    ),
                ),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rules",
                        to="consent.socialconsentcategory",
                    ),
                ),
            ],
            options={
                "verbose_name": "Social Consent Category Rule",
                "verbose_name_plural": "Social Consent Category Rules",
                "unique_together": {("preference", "category")},
            },
        ),
        # 4. Drop old unique_together on SocialConsentWhitelist before adding category FK
        migrations.AlterUniqueTogether(
            name="socialconsentwhitelist",
            unique_together=set(),
        ),
        # 5. Add category FK to SocialConsentWhitelist
        # Pre-production: no meaningful rows; default=1 is a placeholder sentinel
        # (the old whitelist table is empty in dev). The unique_together below
        # is the real constraint.
        migrations.AddField(
            model_name="socialconsentwhitelist",
            name="category",
            field=models.ForeignKey(
                help_text="Allowlist is scoped per category.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="whitelist_entries",
                to="consent.socialconsentcategory",
                default=None,
                null=True,
            ),
            preserve_default=False,
        ),
        # 6. Make category non-nullable
        migrations.AlterField(
            model_name="socialconsentwhitelist",
            name="category",
            field=models.ForeignKey(
                help_text="Allowlist is scoped per category.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="whitelist_entries",
                to="consent.socialconsentcategory",
            ),
        ),
        # 7. Restore unique_together with category included
        migrations.AlterUniqueTogether(
            name="socialconsentwhitelist",
            unique_together={("owner_tenure", "allowed_tenure", "category")},
        ),
    ]
