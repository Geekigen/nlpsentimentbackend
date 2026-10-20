import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def stars_for(score: float) -> int:
    if score >= 0.6:
        return 5
    if score >= 0.2:
        return 4
    if score >= -0.2:
        return 3
    if score >= -0.6:
        return 2
    return 1


def aspects_for(sentiment: str) -> dict:
    if sentiment == "positive":
        rating = "positive"
    elif sentiment == "negative":
        rating = "negative"
    else:
        rating = "neutral"
    noted = {"rating": rating, "note": ""}
    silent = {"rating": "not_mentioned", "note": ""}
    return {
        "punctuality": noted,
        "courtesy": noted,
        "package_care": silent,
        "communication": noted,
        "professionalism": noted,
    }


# employee code, customer, score, sentiment, body (each body stays under 250 characters)
NEW_COMMENTS = [
    ("DRV-014", "Achieng", 0.9, "positive", "Amina called from the gate, waited while I came down, and passed the box over without a scratch."),
    ("DRV-014", "Otieno", 0.92, "positive", "On time, greeted me by name, and set the parcel just inside the door so it stayed dry."),
    ("DRV-014", "Njoki", 0.88, "positive", "Texted when she was five minutes away and handed the package over carefully."),
    ("DRV-014", "Mwangi", 0.85, "positive", "Polite at the door, patient while I found my ID, and the seal on the box was intact."),
    ("DRV-014", "Wairimu", 0.91, "positive", "Arrived inside the window, knocked gently, and kept the parcel covered in the drizzle."),
    ("DRV-014", "Kiprop", 0.87, "positive", "Confirmed the flat number, smiled, and made sure I had a firm grip on the box."),
    ("DRV-014", "Chebet", 0.84, "positive", "A few minutes early, courteous, and the packaging was untouched when I opened it."),
    ("DRV-014", "Barasa", 0.9, "positive", "Rang once, waited, and told me where she had parked so I could find her quickly."),
    ("DRV-014", "Akinyi", 0.93, "positive", "Professional from the call to the handoff. Nothing was crushed, torn, or missing."),
    ("DRV-014", "Mutiso", 0.86, "positive", "Patient in the rain, kept the bag covered, and thanked me on the way out."),
    ("DRV-014", "Nafula", 0.89, "positive", "Clear updates, careful handling, and a friendly goodbye at the door."),
    ("DRV-014", "Kariuki", 0.94, "positive", "Double-checked my name before releasing the parcel. Calm and professional throughout."),
    ("DRV-014", "Adhiambo", 0.9, "positive", "Smooth drop-off: on time, polite, and the box looked the same as when it was packed."),
    ("DRV-052", "Wanjala", 0.8, "positive", "Faith was on time, polite, and set the parcel down carefully in the hallway."),
    ("DRV-052", "Cheruiyot", 0.82, "positive", "Called ahead, found the right gate, and waited while I came out to sign."),
    ("DRV-052", "Atieno", 0.78, "positive", "Friendly at the door and the package was dry and unopened. No fuss at all."),
    ("DRV-052", "Maina", 0.8, "positive", "Arrived when promised and handed the box over instead of leaving it in the rain."),
    ("DRV-052", "Jelimo", 0.76, "positive", "Courteous, quick, and she confirmed the name on the label before letting go."),
    ("DRV-052", "Omondi", 0.84, "positive", "Texted from the street, then walked the parcel up. Nothing was dented."),
    ("DRV-052", "Wambui", 0.79, "positive", "Professional and patient while the lift was slow. The seal was still intact."),
    ("DRV-052", "Kiptoo", 0.81, "positive", "Clear communication and a careful handoff. I would be glad to see her again."),
    ("DRV-052", "Nyambura", 0.4, "mixed", "Polite and on time, though I had to repeat the flat number once."),
    ("DRV-052", "Were", 0.35, "mixed", "The parcel was fine. Faith was friendly but a little rushed at the door."),
    ("DRV-052", "Chepngeno", 0.42, "mixed", "Arrived inside the window and was courteous. She did not say much else."),
    ("DRV-052", "Odhiambo", 0.38, "mixed", "Careful with the box, a brief hello, and then gone. No problems, nothing extra."),
    ("DRV-033", "Awuor", 0.45, "mixed", "Linet was roughly on time and polite. The box had a small scuff on one corner."),
    ("DRV-033", "Kimani", 0.4, "mixed", "She called once, then handed the parcel over. Fine overall, a bit hurried."),
    ("DRV-033", "Nasimiyu", 0.48, "mixed", "Courteous drop-off. I had to point out the right door, but the parcel was safe."),
    ("DRV-033", "Gitonga", 0.42, "mixed", "Inside the delivery window and the bag was intact. Conversation was short."),
    ("DRV-033", "Moraa", 0.36, "mixed", "Polite enough. She left the parcel with the guard after I said that was fine."),
    ("DRV-033", "Okello", 0.0, "neutral", "The driver left the parcel at the reception desk. I did not meet them."),
    ("DRV-033", "Waceke", 0.05, "neutral", "Delivery was this afternoon. I was out, so I cannot speak to how it was handled."),
    ("DRV-033", "Lagat", -0.05, "neutral", "The parcel was at the door when I got home. No note and no call either way."),
    ("DRV-033", "Nyongesa", 0.0, "neutral", "Someone from the team dropped it with the shop downstairs. That was the whole visit."),
    ("DRV-033", "Chepkemoi", 0.1, "neutral", "It arrived during the stated window. I only saw the parcel, not the driver."),
    ("DRV-041", "Mutua", 0.0, "neutral", "David left the box with security. I have nothing else to say about the drop-off."),
    ("DRV-041", "Aoko", 0.08, "neutral", "The delivery showed up today. I was in a meeting and did not see the driver."),
    ("DRV-041", "Koech", -0.1, "neutral", "Parcel was by the gate when I looked. No message, no complaint either."),
    ("DRV-041", "Waithera", 0.0, "neutral", "Handed to the neighbour as I asked yesterday. I did not meet David myself."),
    ("DRV-041", "Simiyu", -0.45, "negative", "Half an hour late and short with me, though the parcel itself was undamaged."),
    ("DRV-041", "Naliaka", -0.5, "negative", "He did not call, and I had to walk down after the buzzer failed once."),
    ("DRV-041", "Korir", -0.4, "negative", "The box was dusty and he seemed impatient while I checked the label."),
    ("DRV-041", "Makena", -0.55, "negative", "Late, hard to understand on the phone, and he left before I could ask a question."),
    ("DRV-027", "Juma", -0.9, "negative", "No call, very late, and the bag was torn when Brian finally reached the door."),
    ("DRV-027", "Wangari", -0.85, "negative", "He missed the window by over an hour and did not answer two calls."),
    ("DRV-027", "Ochieng", -0.92, "negative", "The carton was crushed and he shrugged when I pointed at the damage."),
    ("DRV-027", "Chemutai", -0.88, "negative", "Rude at the gate, late, and the parcel was left in a puddle."),
    ("DRV-027", "Mwende", -0.8, "negative", "Wrong building first, then no apology. The tape on the box was split open."),
]


def seed_ratings(apps, schema_editor):
    Driver = apps.get_model("comments", "Driver")
    Delivery = apps.get_model("comments", "Delivery")
    Comment = apps.get_model("comments", "Comment")

    for comment in Comment.objects.all():
        reference = (comment.order_reference or f"DEL-LEGACY-{comment.pk}").strip() or f"DEL-LEGACY-{comment.pk}"
        candidate = reference
        suffix = 2
        while Delivery.objects.filter(reference=candidate).exists():
            candidate = f"{reference}-{suffix}"
            suffix += 1
        delivery = Delivery.objects.create(driver_id=comment.driver_id, reference=candidate)
        comment.delivery_id = delivery.pk
        comment.stars = stars_for(comment.score)
        comment.save(update_fields=["delivery", "stars"])

    Driver.objects.get_or_create(employee_code="DRV-041", defaults={"name": "David Kamau"})
    Driver.objects.get_or_create(employee_code="DRV-052", defaults={"name": "Faith Njeri"})

    before = Comment.objects.count()
    room = max(0, 50 - before)
    drivers = {driver.employee_code: driver for driver in Driver.objects.all()}

    for index, (code, customer, score, sentiment, body) in enumerate(NEW_COMMENTS[:room], start=1):
        if len(body) > 250:
            raise ValueError(f"Seed comment {index} is {len(body)} characters.")
        driver = drivers[code]
        delivery = Delivery.objects.create(driver=driver, reference=f"DEL-{index:04d}")
        Comment.objects.create(
            driver=driver,
            delivery=delivery,
            customer_name=customer,
            body=body,
            sentiment=sentiment,
            score=score,
            stars=stars_for(score),
            summary=f"Seeded {sentiment} comment about {driver.name}.",
            aspects=aspects_for(sentiment),
            highlights=[body.split(",")[0][:80]],
            model_name="seed",
        )

    if before <= 2 and Comment.objects.count() != 50:
        raise RuntimeError(f"Expected 50 comments after seeding, found {Comment.objects.count()}.")
    if before <= 2 and Delivery.objects.count() != 50:
        raise RuntimeError(f"Expected 50 deliveries after seeding, found {Delivery.objects.count()}.")


def unseed_ratings(apps, schema_editor):
    Driver = apps.get_model("comments", "Driver")
    Delivery = apps.get_model("comments", "Delivery")
    Comment = apps.get_model("comments", "Comment")
    Comment.objects.update(delivery=None, stars=None)
    Delivery.objects.all().delete()
    Driver.objects.filter(employee_code__in=["DRV-041", "DRV-052"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("comments", "0002_seed_drivers"),
    ]

    operations = [
        migrations.CreateModel(
            name="Delivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reference", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "driver",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deliveries",
                        to="comments.driver",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="comment",
            name="delivery",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="comments",
                to="comments.delivery",
            ),
        ),
        migrations.AddField(
            model_name="comment",
            name="stars",
            field=models.PositiveSmallIntegerField(null=True),
        ),
        migrations.AlterField(
            model_name="comment",
            name="body",
            field=models.TextField(
                max_length=250,
                validators=[django.core.validators.MaxLengthValidator(250)],
            ),
        ),
        migrations.RunPython(seed_ratings, unseed_ratings),
        migrations.AlterField(
            model_name="comment",
            name="delivery",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="comments",
                to="comments.delivery",
            ),
        ),
        migrations.AlterField(
            model_name="comment",
            name="stars",
            field=models.PositiveSmallIntegerField(
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(5),
                ],
            ),
        ),
        migrations.AddConstraint(
            model_name="comment",
            constraint=models.CheckConstraint(
                condition=models.Q(stars__gte=1, stars__lte=5),
                name="comment_stars_range",
            ),
        ),
    ]
