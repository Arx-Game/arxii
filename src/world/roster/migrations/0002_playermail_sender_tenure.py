from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("roster", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="playermail",
            name="sender_tenure",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="sent_mail",
                to="roster.rostertenure",
                help_text="Tenure used when sending the mail",
            ),
        ),
    ]
