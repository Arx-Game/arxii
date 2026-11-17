"""Remove the old Rite of Atonement's schema: its conversion rate and PENANCE grants (#4751).

Schema only (the Ritual row is deleted in 0449).

``FallRedemptionConfig.penance_exchange_rate`` was the old rite's one tuning number; its
disposition (ADR-0237) is a deliberate discard. The ``PENANCE`` grant source and its shape
constraint go too: no route could write a PENANCE grant, since the rite could not be
performed. Dropping the constraint cannot fail on existing rows.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0447_affinity_unsettled_step_percent_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="resonancegrant",
            name="res_grant_penance_shape",
        ),
        migrations.RemoveField(
            model_name="fallredemptionconfig",
            name="penance_exchange_rate",
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
                ],
                help_text="Discriminator. Identifies which source_* FK is populated.",
                max_length=32,
            ),
        ),
    ]
