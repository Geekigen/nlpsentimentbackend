from django.db.models import Avg, Count, FloatField, Q, Value
from django.db.models.functions import Coalesce

from comments.models import Driver

ASPECT_KEYS = (
    "punctuality",
    "courtesy",
    "package_care",
    "communication",
    "professionalism",
)


def score_to_stars(score: float) -> int:
    """Map a classifier score from -1..1 onto an integer rating from 1..5."""
    if score >= 0.6:
        return 5
    if score >= 0.2:
        return 4
    if score >= -0.2:
        return 3
    if score >= -0.6:
        return 2
    return 1


def annotated_drivers():
    scored = Q(comments__analysis_status="analyzed")
    return (
        Driver.objects.annotate(
            comment_count=Count("comments", filter=scored),
            average_score=Avg("comments__score", filter=scored),
            average_stars=Avg("comments__stars", filter=scored),
            positive_count=Count("comments", filter=scored & Q(comments__sentiment="positive")),
            negative_count=Count("comments", filter=scored & Q(comments__sentiment="negative")),
            neutral_count=Count("comments", filter=scored & Q(comments__sentiment="neutral")),
            mixed_count=Count("comments", filter=scored & Q(comments__sentiment="mixed")),
        )
        .annotate(star_sort=Coalesce("average_stars", Value(-1.0), output_field=FloatField()))
        .order_by("-star_sort", "-comment_count", "name")
    )


def ranked_drivers():
    return annotated_drivers().filter(comment_count__gt=0)


def dominant_sentiment(driver) -> str | None:
    counts = {
        "positive": driver.positive_count,
        "negative": driver.negative_count,
        "mixed": driver.mixed_count,
        "neutral": driver.neutral_count,
    }
    best = max(counts, key=counts.get)
    if counts[best] == 0:
        return None
    return best


def resolve_driver(token: str) -> Driver:
    value = token.strip()
    if not value:
        raise Driver.DoesNotExist("A driver id, employee code, or name is required.")

    queryset = Driver.objects.all()
    if value.isdigit():
        match = queryset.filter(pk=int(value)).first()
        if match:
            return match

    match = queryset.filter(employee_code__iexact=value).first()
    if match:
        return match

    matches = list(queryset.filter(name__icontains=value)[:5])
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = ", ".join(driver.employee_code for driver in matches)
        raise Driver.MultipleObjectsReturned(f"Multiple drivers match. Use an employee code: {names}.")
    raise Driver.DoesNotExist(f"No driver matches '{value}'.")


def aspect_breakdown(driver: Driver) -> dict:
    totals = {key: {"positive": 0, "negative": 0, "neutral": 0, "not_mentioned": 0} for key in ASPECT_KEYS}
    for comment in driver.comments.filter(analysis_status="analyzed"):
        aspects = comment.aspects or {}
        for key in ASPECT_KEYS:
            rating = (aspects.get(key) or {}).get("rating", "not_mentioned")
            if rating not in totals[key]:
                rating = "not_mentioned"
            totals[key][rating] += 1
    return totals
