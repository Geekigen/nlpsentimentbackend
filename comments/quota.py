from django.db import transaction
from django.db.models import F

from comments.models import ADMIN_ASK_LIMIT, AskQuota


class AskLimitReached(Exception):
    detail = "Only 15 chat requests."


def asks_remaining(user) -> int | None:
    if user.is_superuser:
        return None
    quota = AskQuota.objects.filter(user=user).first()
    used = quota.used if quota else 0
    return max(ADMIN_ASK_LIMIT - used, 0)


def consume_ask(user) -> int | None:
    """Count one chat for a staff admin. Superusers are unlimited."""
    if user.is_superuser:
        return None
    with transaction.atomic():
        quota, _ = AskQuota.objects.get_or_create(user=user)
        updated = AskQuota.objects.filter(pk=quota.pk, used__lt=ADMIN_ASK_LIMIT).update(used=F("used") + 1)
        if not updated:
            raise AskLimitReached()
        quota.refresh_from_db()
    return ADMIN_ASK_LIMIT - quota.used
