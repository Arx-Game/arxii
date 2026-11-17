# Burden reflections and the settling of the Mire, part one (#5177). Schema-only: the
# reflection's tether column, the new SoulTetherConfig sizes, the new gain sources and the
# shape of a SUCCUMBED grant. Part two (0454) adds the reflection constraints that pair the
# new column with old ones, so the constraint meets a column that already exists.
# Data disposition (ADR-0237): nothing is dropped; every new column is nullable or defaulted.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0454_remove_sineating_costs"),
    ]

    operations = [
        migrations.AddField(
            model_name="reflection",
            name="tether",
            field=models.ForeignKey(
                blank=True,
                help_text="The Sineater's own side of the tether whose Mire is reflected on. Set one of grant, resonance, tether.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="burden_reflections",
                to="arxii.characterrelationship",
            ),
        ),
        migrations.AddField(
            model_name="soultetherconfig",
            name="absolve_affection",
            field=models.PositiveIntegerField(
                default=5,
                help_text="Affection the Sineater gains toward the Sinner when they absolve, at a full share of the settling rite.",
            ),
        ),
        migrations.AddField(
            model_name="soultetherconfig",
            name="condemn_conflict",
            field=models.PositiveIntegerField(
                default=5,
                help_text="Conflict the Sineater gains toward the Sinner when they condemn, at a full share of the settling rite.",
            ),
        ),
        migrations.AddField(
            model_name="soultetherconfig",
            name="fall_breaker_bonus_percent",
            field=models.PositiveIntegerField(
                default=50,
                help_text="Extra percent on top of the fall's payout for the Sinner of the most recent succumbing, who tipped the Sineater over (50 pays half as much again).",
            ),
        ),
        migrations.AddField(
            model_name="soultetherconfig",
            name="fall_payout_percent",
            field=models.PositiveIntegerField(
                default=300,
                help_text="When a Sineater falls to the Abyss, the percent of what they succumbed to each Sinner since their last fall that this Sinner earns.",
            ),
        ),
        migrations.AddField(
            model_name="soultetherconfig",
            name="jackpot_percent",
            field=models.PositiveIntegerField(
                default=25,
                help_text="When a Sineater succumbs, the percent of everything they purified for this Sinner since the last payout that the Sinner also earns.",
            ),
        ),
        migrations.AddField(
            model_name="soultetherconfig",
            name="purify_reward_percent",
            field=models.PositiveIntegerField(
                default=50,
                help_text="When a Sineater absolves or condemns the Mire they carry, the percent of the corruption cleared that they earn as resonance in their own thread's resonance.",
            ),
        ),
        migrations.AddField(
            model_name="soultetherconfig",
            name="succumb_affection",
            field=models.PositiveIntegerField(
                default=5,
                help_text="Affection the Sineater gains toward the Sinner when they succumb, at a full share of the settling rite.",
            ),
        ),
        migrations.AddField(
            model_name="soultetherconfig",
            name="succumb_bonus_percent",
            field=models.PositiveIntegerField(
                default=200,
                help_text="When a Sineater succumbs, the percent of the amount succumbed that the Sinner earns as resonance in their own thread's resonance (200 pays twice the amount).",
            ),
        ),
        migrations.AddField(
            model_name="soultetherconfig",
            name="succumb_conflict",
            field=models.PositiveIntegerField(
                default=5,
                help_text="Conflict the Sineater gains toward the Sinner when they succumb, at a full share of the settling rite.",
            ),
        ),
        migrations.AlterField(
            model_name="reflection",
            name="choice",
            field=models.CharField(
                choices=[
                    ("EMBRACE", "Embrace"),
                    ("DISOWN", "Disown"),
                    ("ABSOLVE", "Absolve"),
                    ("CONDEMN", "Condemn"),
                    ("SUCCUMB", "Succumb"),
                ],
                max_length=8,
            ),
        ),
        migrations.AlterField(
            model_name="reflection",
            name="grant",
            field=models.ForeignKey(
                blank=True,
                help_text="The deed reflected on. Set one of grant, resonance, tether.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="reflections",
                to="arxii.resonancegrant",
            ),
        ),
        migrations.AlterField(
            model_name="reflection",
            name="resonance",
            field=models.ForeignKey(
                blank=True,
                help_text="The unsettling resonance reflected on. Set one of grant, resonance, tether.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reflections",
                to="arxii.resonance",
            ),
        ),
        migrations.AlterField(
            model_name="resonancegrant",
            name="source",
            field=models.CharField(
                choices=[
                    ("POSE_ENDORSEMENT", "Pose endorsement"),
                    ("SCENE_ENTRY", "Scene entry endorsement"),
                    ("ROOM_RESIDENCE", "Room residence trickle"),
                    ("OUTFIT_TRICKLE", "Outfit trickle"),
                    ("STAFF_GRANT", "Staff grant"),
                    ("SANCTUM_WEAVING", "Sanctum weaving payout"),
                    ("SANCTUM_OWNER_BONUS", "Sanctum owner/member bonus"),
                    ("PROJECT_CONTRIBUTION", "Project contribution payout"),
                    ("SANCTUM_DISSOLUTION_RECOVERY", "Sanctum dissolution recovery"),
                    ("ENTRY_FLOURISH", "Entry flourishing"),
                    ("DRAMATIC_MOMENT", "Dramatic moment"),
                    ("STYLE_PRESENTATION", "Style presentation"),
                    ("MISSION_REWARD", "Mission reward"),
                    ("MISSION_REPORT", "Mission report style"),
                    ("STAKE_REWARD", "Stake reward"),
                    ("DISTINCTION", "Distinction"),
                    ("COMBO_DISCOVERY", "Combo discovery"),
                    ("COMPROMISE", "Moral compromise"),
                    ("FALL_CONVERSION", "Fall/Redemption conversion"),
                    ("WORSHIP_RITE", "Worship rite"),
                    ("DRIFT_CORRECTION", "Drift correction"),
                    ("CORRUPTION_CLEANSING", "Corruption cleansing payout"),
                    ("SINEATING", "Sineating payout"),
                    ("CHARACTER_CREATION", "Character creation"),
                    ("KINDLED_DEED", "Kindled deed"),
                    ("EMBRACED_DEED", "Embraced deed"),
                    ("MIRE_PURIFIED", "Mire purified"),
                    ("SUCCUMBED", "Succumbed to the Mire"),
                    ("SUCCUMB_BONUS", "Sineater succumbed bonus"),
                    ("SINEATER_FALL", "Sineater fell"),
                ],
                help_text="Discriminator. Identifies which source_* FK is populated.",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="resonancegrant",
            name="source_reflection",
            field=models.ForeignKey(
                blank=True,
                help_text="Set when source is EMBRACED_DEED (#5124) or SUCCUMBED (#5177); the reflection the rite applied.",
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="resonance_grants",
                to="arxii.reflection",
            ),
        ),
        migrations.AlterField(
            model_name="resonancegrant",
            name="source_settling_rite",
            field=models.ForeignKey(
                blank=True,
                help_text="Set when source is EMBRACED_DEED (#5124) or SUCCUMBED (#5177); the rite that applied the reflection.",
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="resonance_grants",
                to="arxii.settlingrite",
            ),
        ),
        migrations.AddConstraint(
            model_name="resonancegrant",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("source", "SUCCUMBED"),
                        ("source_settling_rite__isnull", False),
                        ("source_reflection__isnull", False),
                        ("source_room_profile__isnull", True),
                        ("source_staff_account__isnull", True),
                        ("source_pose_endorsement__isnull", True),
                        ("source_scene_entry_endorsement__isnull", True),
                        ("outfit_item_facet__isnull", True),
                        ("source_sanctum_details__isnull", True),
                        ("source_project__isnull", True),
                        ("source_entry_flourish__isnull", True),
                        ("source_dramatic_moment__isnull", True),
                        ("source_style_presentation_endorsement__isnull", True),
                        ("source_mission_deed_reward_line__isnull", True),
                        ("source_character_distinction__isnull", True),
                        ("source_worship_rite_performance__isnull", True),
                        ("source_kindling_situation__isnull", True),
                    ),
                    models.Q(("source", "SUCCUMBED"), _negated=True),
                    _connector="OR",
                ),
                name="res_grant_succumbed_shape",
            ),
        ),
    ]
