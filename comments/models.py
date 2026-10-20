from django.conf import settings
from django.core.validators import MaxLengthValidator, MaxValueValidator, MinValueValidator
from django.db import models

ADMIN_ASK_LIMIT = 15


class Driver(models.Model):
    name = models.CharField(max_length=120)
    employee_code = models.CharField(max_length=32, unique=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.employee_code})"


class Delivery(models.Model):
    driver = models.ForeignKey(Driver, related_name="deliveries", on_delete=models.CASCADE)
    reference = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} ({self.driver.employee_code})"


class Comment(models.Model):
    class Sentiment(models.TextChoices):
        POSITIVE = "positive", "Positive"
        NEGATIVE = "negative", "Negative"
        NEUTRAL = "neutral", "Neutral"
        MIXED = "mixed", "Mixed"

    class AnalysisStatus(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        ANALYZING = "analyzing", "Analyzing"
        ANALYZED = "analyzed", "Analyzed"

    driver = models.ForeignKey(Driver, related_name="comments", on_delete=models.CASCADE)
    delivery = models.ForeignKey(Delivery, related_name="comments", on_delete=models.CASCADE)
    customer_name = models.CharField(max_length=120, blank=True)
    order_reference = models.CharField(max_length=64, blank=True)
    body = models.TextField(max_length=250, validators=[MaxLengthValidator(250)])
    analysis_status = models.CharField(
        max_length=16,
        choices=AnalysisStatus.choices,
        default=AnalysisStatus.SUBMITTED,
    )
    sentiment = models.CharField(max_length=16, choices=Sentiment.choices, blank=True, null=True)
    score = models.FloatField(blank=True, null=True)
    stars = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        blank=True,
        null=True,
    )
    summary = models.TextField(blank=True)
    aspects = models.JSONField(default=dict, blank=True)
    highlights = models.JSONField(default=list, blank=True)
    model_name = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(stars__gte=1, stars__lte=5) | models.Q(stars__isnull=True),
                name="comment_stars_range",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.delivery_id:
            self.driver_id = self.delivery.driver_id
        if self.score is not None:
            from comments.queries import score_to_stars

            self.stars = score_to_stars(float(self.score))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.driver.employee_code} {self.stars}★ {self.sentiment}"


class AskQuota(models.Model):
    """Chat questions used by an admin created in Django. Superusers are not counted."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="ask_quota",
        on_delete=models.CASCADE,
    )
    used = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.user} {self.used}/{ADMIN_ASK_LIMIT}"
