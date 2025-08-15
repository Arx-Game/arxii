from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("roster", "0002_playermail_sender_tenure"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="playermail",
            name="roster_play_sender__2c3255_idx",
        ),
        migrations.RemoveField(
            model_name="playermail",
            name="sender_account",
        ),
        migrations.RemoveField(
            model_name="playermail",
            name="sender_character",
        ),
        migrations.AddIndex(
            model_name="playermail",
            index=models.Index(
                fields=["sender_tenure", "sent_date"],
                name="roster_playermail_sender_tenure_sent_date_idx",
            ),
        ),
    ]
