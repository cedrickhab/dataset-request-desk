from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("desk", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="DemoSeedRecord",
            fields=[
                ("key", models.CharField(max_length=100, primary_key=True, serialize=False)),
                ("request", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, to="desk.datasetrequest")),
            ],
        ),
    ]
