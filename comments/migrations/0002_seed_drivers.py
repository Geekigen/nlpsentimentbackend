from django.db import migrations


def seed_drivers(apps, schema_editor):
    Driver = apps.get_model("comments", "Driver")
    Comment = apps.get_model("comments", "Comment")

    amina = Driver.objects.create(name="Amina Yusuf", employee_code="DRV-014")
    brian = Driver.objects.create(name="Brian Otieno", employee_code="DRV-027")
    Driver.objects.create(name="Linet Wanjiku", employee_code="DRV-033")

    positive = {"rating": "positive", "note": ""}
    negative = {"rating": "negative", "note": ""}
    silent = {"rating": "not_mentioned", "note": ""}

    Comment.objects.create(
        driver=amina,
        customer_name="Wanjiru",
        order_reference="ORD-1042",
        body="Amina called before arriving, waited while I came downstairs, and handed the parcel over carefully.",
        sentiment="positive",
        score=0.86,
        summary="The driver communicated ahead, was patient, and handled the parcel with care.",
        aspects={
            "punctuality": silent,
            "courtesy": {**positive, "note": "Waited downstairs."},
            "package_care": {**positive, "note": "Handed the parcel over carefully."},
            "communication": {**positive, "note": "Called before arriving."},
            "professionalism": positive,
        },
        highlights=["called before arriving", "handed the parcel over carefully"],
        model_name="seed",
    )
    Comment.objects.create(
        driver=brian,
        customer_name="Kamau",
        order_reference="ORD-1108",
        body="The driver was an hour late, did not answer my calls, and the box was crushed when it arrived.",
        sentiment="negative",
        score=-0.78,
        summary="The driver was late, unreachable, and delivered a damaged box.",
        aspects={
            "punctuality": {**negative, "note": "An hour late."},
            "courtesy": silent,
            "package_care": {**negative, "note": "The box was crushed."},
            "communication": {**negative, "note": "Did not answer calls."},
            "professionalism": negative,
        },
        highlights=["an hour late", "did not answer my calls", "box was crushed"],
        model_name="seed",
    )


def unseed_drivers(apps, schema_editor):
    Driver = apps.get_model("comments", "Driver")
    Driver.objects.filter(employee_code__in=["DRV-014", "DRV-027", "DRV-033"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("comments", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_drivers, unseed_drivers),
    ]
