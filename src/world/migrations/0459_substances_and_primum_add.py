"""Substances and Primum (#5125): every new table and column, schema-only.

No operation removes or rewrites anything and no row is written. The ``Gift.substance``
check constraint is the next migration, since it pairs the new column with ``kind``.
The old ``GiftSubstance`` rows move onto ``Substance`` in a later data migration.
"""

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone

import core.natural_keys


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0458_remove_mire_share_of_the_aura"),
    ]

    operations = [
        migrations.CreateModel(
            name="SubstancePowerStep",
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
                    "points_reached",
                    models.PositiveIntegerField(
                        help_text="The summed Primum points a caster must reach for this much power.",
                        unique=True,
                    ),
                ),
                (
                    "power",
                    models.PositiveSmallIntegerField(
                        help_text="The power a caster who reaches these points gains."
                    ),
                ),
            ],
            options={
                "ordering": ["points_reached"],
            },
            bases=(core.natural_keys.NaturalKeyMixin, models.Model),
        ),
        migrations.CreateModel(
            name="SubstanceRelation",
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
                    "kind",
                    models.CharField(
                        choices=[("related", "Related"), ("opposed", "Opposed")],
                        help_text="Related: a caster of one gets a share of the other's benefit. Opposed: the other works against the caster's own.",
                        max_length=10,
                    ),
                ),
            ],
            bases=(core.natural_keys.NaturalKeyMixin, models.Model),
        ),
        migrations.AddField(
            model_name="combatopponent",
            name="primum_harvested_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When this slain creature's Primum was harvested (#5125). A slain creature is harvested once; null means it has not been.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="consequenceeffect",
            name="primum_reveal",
            field=models.CharField(
                blank=True,
                choices=[
                    ("strongest", "The strongest substance"),
                    ("all", "Every substance"),
                ],
                default="",
                help_text="REVEAL_PRIMUM: how much of the Primum in the place the character perceives. The strongest substance only, or every substance.",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="craftingmaterialrequirement",
            name="is_optional",
            field=models.BooleanField(
                default=False,
                help_text="An optional ingredient (#5125): the craft goes ahead without it, and when it is staged and consumed it adds to the result, such as a Primum item that gives the made item a substance.",
            ),
        ),
        migrations.AddField(
            model_name="resonanceenvironmentconfig",
            name="harvest_check_type",
            field=models.ForeignKey(
                blank=True,
                help_text="The check a harvester rolls to take Primum. Unset: nothing can be harvested.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="arxii.checktype",
                verbose_name="Check rolled to harvest Primum",
            ),
        ),
        migrations.AddField(
            model_name="resonanceenvironmentconfig",
            name="harvest_skill",
            field=models.ForeignKey(
                blank=True,
                error_messages={
                    "invalid": "Choose a skill in the Magic category that is not a combat style's skill. A magical roll adds only skills made for magic, so it never counts a skill a character picks elsewhere."
                },
                help_text="The magical skill a harvester adds to the harvest roll. Magic-category skills only, never a combat style's skill. Unset: nothing can be harvested.",
                limit_choices_to=models.Q(
                    ("category", "magic"),
                    ("trait_type", "skill"),
                    ("combat_style__isnull", True),
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="arxii.skill",
                verbose_name="Skill added to the harvest roll",
            ),
        ),
        migrations.AddField(
            model_name="resonanceenvironmentconfig",
            name="harvest_thread_bonus",
            field=models.PositiveSmallIntegerField(
                default=5,
                help_text="Bonus a harvester gets on the roll for a gift thread of the substance, scaled by her thread level.",
                verbose_name="Harvest bonus from the gift thread",
            ),
        ),
        migrations.AddField(
            model_name="resonanceenvironmentconfig",
            name="harvest_ap_cost",
            field=models.PositiveSmallIntegerField(
                default=2,
                help_text="Action points every attempt to harvest Primum costs, good roll or bad. A character without them is refused before she rolls. 0: free.",
                verbose_name="Action points one harvest attempt costs",
            ),
        ),
        migrations.AddField(
            model_name="resonanceenvironmentconfig",
            name="harvest_fatigue_cost",
            field=models.PositiveSmallIntegerField(
                default=2,
                help_text="Physical fatigue every attempt to harvest Primum adds, good roll or bad, after the usual fatigue rules. 0: none.",
                verbose_name="Physical fatigue one harvest attempt costs",
            ),
        ),
        migrations.AddField(
            model_name="resonanceenvironmentconfig",
            name="substance_call_up_anima",
            field=models.PositiveSmallIntegerField(
                default=3,
                help_text="Anima one call-up costs, raising the place's Primum by one step. Shared by every caster who calls it up together; never refused for lack of anima.",
                verbose_name="Anima to call up Primum",
            ),
        ),
        migrations.AddField(
            model_name="resonanceenvironmentconfig",
            name="substance_power_cap",
            field=models.PositiveSmallIntegerField(
                default=12,
                help_text="The most power all of a caster's Primum sources add together, before her gift thread scales it.",
                verbose_name="Most power Primum can add",
            ),
        ),
        migrations.AddField(
            model_name="resonanceenvironmentconfig",
            name="substance_related_share_pct",
            field=models.PositiveSmallIntegerField(
                default=50,
                help_text="How much of a Primum source's benefit a caster gets from a substance related to her gift's own, as a percent. A matching substance gives full benefit. 0 to 100.",
                validators=[django.core.validators.MaxValueValidator(100)],
                verbose_name="Related substance gives (% of full benefit)",
            ),
        ),
        migrations.AlterField(
            model_name="consequenceeffect",
            name="effect_type",
            field=models.CharField(
                choices=[
                    ("apply_condition", "Apply Condition"),
                    ("remove_condition", "Remove Condition"),
                    ("set_relationship_condition", "Set Relationship Condition"),
                    ("shift_affection", "Shift Affection"),
                    ("shift_npc_regard", "Shift NPC Regard"),
                    ("add_property", "Add Property"),
                    ("remove_property", "Remove Property"),
                    ("grant_distinction", "Grant Distinction"),
                    ("deal_damage", "Deal Damage"),
                    ("launch_attack", "Launch Attack"),
                    ("launch_flow", "Launch Flow"),
                    ("grant_codex", "Grant Codex Entry"),
                    ("grant_secret", "Grant Secret Knowledge"),
                    ("magical_scars", "Mage Scars"),
                    ("legend_award", "Award Legend"),
                    ("capture", "Capture"),
                    ("escape_captivity", "Escape Captivity"),
                    ("rescue_captive", "Rescue Captive"),
                    ("create_position", "Create Position"),
                    ("move_to_position", "Move to Position"),
                    ("sever_edge", "Sever Edge"),
                    ("connect_edge", "Connect Edge"),
                    ("grant_flight", "Grant Flight"),
                    ("remove_flight", "Remove Flight"),
                    ("asset_status", "Asset Status"),
                    ("restore_fatigue", "Restore Fatigue"),
                    ("restore_anima", "Restore Anima"),
                    ("intoxicate", "Intoxicate"),
                    ("technique_training", "Technique Training"),
                    ("reveal_primum", "Reveal Primum"),
                ],
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="giftsubstance",
            name="gift",
            field=models.OneToOneField(
                help_text="The gift this is the substance of.",
                on_delete=django.db.models.deletion.CASCADE,
                primary_key=True,
                related_name="legacy_substance",
                serialize=False,
                to="arxii.gift",
            ),
        ),
        migrations.CreateModel(
            name="HarvestOutcome",
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
                    "amount_taken",
                    models.PositiveIntegerField(
                        help_text="Primum taken out of the place or creature at this outcome."
                    ),
                ),
                (
                    "quantity",
                    models.PositiveSmallIntegerField(
                        help_text="How many Primum items the harvester receives at this outcome."
                    ),
                ),
                (
                    "outcome_tier",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="%(app_label)s_%(class)s",
                        to="arxii.checkoutcome",
                    ),
                ),
                (
                    "quality_tier",
                    models.ForeignKey(
                        help_text="The quality tier of the Primum items received.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="arxii.qualitytier",
                    ),
                ),
            ],
            options={
                "ordering": ["outcome_tier__success_level"],
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="PrimumStep",
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
                    "rank",
                    models.PositiveSmallIntegerField(
                        help_text="The order of the step (1, 2, 3...). Code knows only this.",
                        unique=True,
                        validators=[django.core.validators.MinValueValidator(1)],
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="The word players read for this step.",
                        max_length=50,
                        unique=True,
                    ),
                ),
                (
                    "starts_at",
                    models.PositiveIntegerField(
                        help_text="The least Primum a place or creature holds to read as this step.",
                        unique=True,
                    ),
                ),
                (
                    "points",
                    models.PositiveSmallIntegerField(
                        help_text="The power points a source at this step is worth to a caster."
                    ),
                ),
                (
                    "item_quality",
                    models.OneToOneField(
                        blank=True,
                        help_text="The quality tier a crafted Primum item carries at this step. Blank if no crafted item reads as this step.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="primum_step",
                        to="arxii.qualitytier",
                    ),
                ),
            ],
            options={
                "ordering": ["rank"],
            },
            bases=(core.natural_keys.NaturalKeyMixin, models.Model),
        ),
        migrations.CreateModel(
            name="Substance",
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
                    "written_on",
                    models.DateField(
                        blank=True, help_text="Date the prose was written.", null=True
                    ),
                ),
                (
                    "reviewed_on",
                    models.DateField(
                        blank=True, help_text="Date the prose was reviewed.", null=True
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text='What lines and cards call it ("fire", "ice", "shadow").',
                        max_length=60,
                        unique=True,
                    ),
                ),
                (
                    "stat_key",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("crime", "Crime"),
                            ("order", "Order"),
                            ("cleanliness", "Cleanliness"),
                            ("lighting", "Lighting"),
                            ("noise", "Noise"),
                            ("traffic", "Traffic"),
                            ("cold", "Cold exposure"),
                            ("heat", "Heat exposure"),
                            ("wet", "Wet exposure"),
                            ("wind", "Wind exposure"),
                            ("dry", "Dry exposure"),
                            ("amenity", "Amenity (positive comfort)"),
                            ("sun", "Sun protection"),
                        ],
                        help_text="The room condition this substance grows along, such as Lighting for shadow. Leave blank, with the direction, if no room condition feeds it.",
                        max_length=20,
                        verbose_name="Which room condition feeds it",
                    ),
                ),
                (
                    "direction",
                    models.CharField(
                        blank=True,
                        choices=[
                            (
                                "rising",
                                "Higher (wetter, windier or hotter, e.g. water, wind or fire)",
                            ),
                            ("falling", "Lower (darker, e.g. shadow)"),
                        ],
                        help_text="Shadow is stronger when lighting is lower (darker). Water, wind and fire are stronger when wet, wind and heat are higher. Blank when no room condition feeds it.",
                        max_length=10,
                        verbose_name="Stronger when it is",
                    ),
                ),
                (
                    "property",
                    models.ForeignKey(
                        blank=True,
                        help_text="A property every technique of a gift of this substance carries, such as 'shadow'. It cannot be unticked on a technique. Leave blank for none.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="substances",
                        to="arxii.property",
                        verbose_name="Property added to every technique of this gift",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="Who reviewed this row's prose, if anyone. Distinct from writing it.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="arxii.contentcontributor",
                    ),
                ),
                (
                    "written_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="Who wrote this row's prose. Null means it is still a placeholder.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="arxii.contentcontributor",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
            bases=(core.natural_keys.NaturalKeyMixin, models.Model),
        ),
        migrations.CreateModel(
            name="PrimumSighting",
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
                    "character_sheet",
                    models.ForeignKey(
                        help_text="The character who perceived it.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="primum_sightings",
                        to="arxii.charactersheet",
                    ),
                ),
                (
                    "room_profile",
                    models.ForeignKey(
                        help_text="The place it was perceived in.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="primum_sightings",
                        to="arxii.roomprofile",
                    ),
                ),
                (
                    "substance",
                    models.ForeignKey(
                        help_text="The substance perceived.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sightings",
                        to="arxii.substance",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="PrimumCallUp",
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
                    "amount_added",
                    models.PositiveIntegerField(
                        help_text="The Primum the call-up added to the place."
                    ),
                ),
                (
                    "caster",
                    models.ForeignKey(
                        blank=True,
                        help_text="The caster who called it up. Set exactly one of caster and scene.",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="primum_call_ups",
                        to="arxii.charactersheet",
                    ),
                ),
                (
                    "room_profile",
                    models.ForeignKey(
                        help_text="The place the Primum was called up in.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="primum_call_ups",
                        to="arxii.roomprofile",
                    ),
                ),
                (
                    "scene",
                    models.ForeignKey(
                        blank=True,
                        help_text="The scene the call-up lasts for. Set exactly one of caster and scene.",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="primum_call_ups",
                        to="arxii.scene",
                    ),
                ),
                (
                    "substance",
                    models.ForeignKey(
                        help_text="The substance called up.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="call_ups",
                        to="arxii.substance",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="PlacePrimum",
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
                    "capacity",
                    models.PositiveIntegerField(
                        help_text="The most Primum the place can hold of this substance."
                    ),
                ),
                (
                    "stored_amount",
                    models.PositiveIntegerField(
                        help_text=(
                            "How much Primum this place holds. Refill days add to it; "
                            "changing it here starts the refill count again."
                        )
                    ),
                ),
                (
                    "stamped_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        help_text="When the stored amount was last written. Refill counts from here.",
                    ),
                ),
                (
                    "refill_per_day",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Primum the place gains each whole day. 0 means it never refills.",
                    ),
                ),
                (
                    "is_finite",
                    models.BooleanField(
                        default=False,
                        help_text="A finite place never refills, whatever its refill per day.",
                    ),
                ),
                (
                    "room_profile",
                    models.ForeignKey(
                        help_text="The place that holds the Primum.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="primum",
                        to="arxii.roomprofile",
                    ),
                ),
                (
                    "substance",
                    models.ForeignKey(
                        help_text="The substance held.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="places",
                        to="arxii.substance",
                    ),
                ),
            ],
            options={
                "verbose_name": "Place primum",
                "verbose_name_plural": "Place primum",
            },
            bases=(core.natural_keys.NaturalKeyMixin, models.Model),
        ),
        migrations.CreateModel(
            name="ItemSubstance",
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
                    "item_instance",
                    models.ForeignKey(
                        help_text="The item that carries the substance.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="item_substances",
                        to="arxii.iteminstance",
                    ),
                ),
                (
                    "step",
                    models.ForeignKey(
                        help_text="The Primum step the item carries it at.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="item_rows",
                        to="arxii.primumstep",
                    ),
                ),
                (
                    "substance",
                    models.ForeignKey(
                        help_text="The substance the item carries.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="item_rows",
                        to="arxii.substance",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="CreaturePrimum",
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
                    "amount",
                    models.PositiveIntegerField(
                        help_text="The Primum a slain creature of this kind holds."
                    ),
                ),
                (
                    "creature_template",
                    models.ForeignKey(
                        help_text="The creature that carries the Primum.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="primum",
                        to="arxii.creaturetemplate",
                    ),
                ),
                (
                    "substance",
                    models.ForeignKey(
                        help_text="The substance carried.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="creatures",
                        to="arxii.substance",
                    ),
                ),
            ],
            options={
                "verbose_name": "Creature primum",
                "verbose_name_plural": "Creature primum",
            },
            bases=(core.natural_keys.NaturalKeyMixin, models.Model),
        ),
        migrations.AddField(
            model_name="gift",
            name="substance",
            field=models.ForeignKey(
                blank=True,
                help_text="What this gift works through, such as fire or shadow (#5125). Every major gift has one; a minor gift has none. A caster of the gift is stronger where Primum of this substance is held.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="gifts",
                to="arxii.substance",
            ),
        ),
        migrations.AddField(
            model_name="itemtemplate",
            name="primum_substance",
            field=models.ForeignKey(
                blank=True,
                help_text="The substance this template is the Primum item of (#5125). One template per substance. Blank for every other item.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="primum_templates",
                to="arxii.substance",
            ),
        ),
        migrations.AddConstraint(
            model_name="itemtemplate",
            constraint=models.UniqueConstraint(
                condition=models.Q(("primum_substance__isnull", False)),
                fields=("primum_substance",),
                name="itemtemplate_primum_substance_unique",
            ),
        ),
        migrations.AddField(
            model_name="substancerelation",
            name="substance_a",
            field=models.ForeignKey(
                help_text="One of the two substances. The pair is saved in id order.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="arxii.substance",
            ),
        ),
        migrations.AddField(
            model_name="substancerelation",
            name="substance_b",
            field=models.ForeignKey(
                help_text="The other substance.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="arxii.substance",
            ),
        ),
        migrations.AddConstraint(
            model_name="substance",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("stat_key", ""), ("direction", "")),
                    models.Q(
                        models.Q(("stat_key", ""), _negated=True),
                        models.Q(("direction", ""), _negated=True),
                    ),
                    _connector="OR",
                ),
                name="magic_substance_condition_and_direction_together",
            ),
        ),
        migrations.AddConstraint(
            model_name="primumsighting",
            constraint=models.UniqueConstraint(
                fields=("character_sheet", "room_profile", "substance"),
                name="magic_primumsighting_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="primumcallup",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("caster__isnull", False), ("scene__isnull", True)),
                    models.Q(("caster__isnull", True), ("scene__isnull", False)),
                    _connector="OR",
                ),
                name="magic_primumcallup_one_owner",
            ),
        ),
        migrations.AddConstraint(
            model_name="primumcallup",
            constraint=models.UniqueConstraint(
                condition=models.Q(("caster__isnull", False)),
                fields=("room_profile", "substance", "caster"),
                name="magic_primumcallup_caster_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="primumcallup",
            constraint=models.UniqueConstraint(
                condition=models.Q(("scene__isnull", False)),
                fields=("room_profile", "substance", "scene"),
                name="magic_primumcallup_scene_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="placeprimum",
            constraint=models.UniqueConstraint(
                fields=("room_profile", "substance"),
                name="magic_placeprimum_room_substance_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="placeprimum",
            constraint=models.CheckConstraint(
                condition=models.Q(("stored_amount__lte", models.F("capacity"))),
                name="magic_placeprimum_stored_within_capacity",
            ),
        ),
        migrations.AddConstraint(
            model_name="itemsubstance",
            constraint=models.UniqueConstraint(
                fields=("item_instance", "substance"),
                name="items_itemsubstance_item_substance_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="creatureprimum",
            constraint=models.UniqueConstraint(
                fields=("creature_template", "substance"),
                name="magic_creatureprimum_template_substance_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="substancerelation",
            constraint=models.CheckConstraint(
                condition=models.Q(("substance_a__lt", models.F("substance_b"))),
                name="magic_substancerelation_pair_in_order",
            ),
        ),
        migrations.AddConstraint(
            model_name="substancerelation",
            constraint=models.UniqueConstraint(
                fields=("substance_a", "substance_b"),
                name="magic_substancerelation_pair_unique",
            ),
        ),
    ]
