"""Remove Draft* magic models and TraditionTemplate models.

These models are replaced by the cantrip-based magic system.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("character_creation", "0005_beginnings_heritage"),
    ]

    operations = [
        # Drop child tables first (FK dependencies)
        migrations.DeleteModel(name="DraftMotifResonanceAssociation"),
        migrations.DeleteModel(name="DraftMotifResonance"),
        migrations.DeleteModel(name="DraftTechnique"),
        migrations.DeleteModel(name="DraftMotif"),
        migrations.DeleteModel(name="DraftGift"),
        migrations.DeleteModel(name="DraftAnimaRitual"),
        migrations.DeleteModel(name="TraditionTemplateFacet"),
        migrations.DeleteModel(name="TraditionTemplateTechnique"),
        migrations.DeleteModel(name="TraditionTemplate"),
    ]
