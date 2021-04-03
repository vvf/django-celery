import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Q, F, Max
from django.utils import timezone

from elk.celery import app as celery
from mailer.owl import Owl
from market.models import Subscription

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())


@celery.task
def notify_waste_money():
    repeat_notification_time = timezone.now() - timedelta(days=settings.WASTE_MONEY_NOTIFY_NEXT_DELAY_DAYS)
    waste_money_expire_date = timezone.now() - timedelta(days=settings.WASTE_MONEY_NOTIFY_FIRST_DELAY_DAYS)
    due_edge_date = timezone.now() - F('duration')
    expired_subscriptions_empty = Subscription.objects.filter(
        is_fully_used=False,
        first_lesson_date__isnull=True,
    ).filter(
        # not dued
        Q(first_lesson_date__gt=due_edge_date) | Q(first_lesson_date__isnull=True, buy_date__gt=due_edge_date)
    ).filter(
        # not sent that notify before today
        Q(when_waste_money_notification_sent__lt=repeat_notification_time) |
        Q(when_waste_money_notification_sent__isnull=True)
    ).annotate(
        max_lesson_date=Max('classes__timeline__start')
    ).filter(
        Q(max_lesson_date__lte=waste_money_expire_date) |
        Q(max_lesson_date__isnull=True, buy_date__lte=waste_money_expire_date)
    )
    subscription: Subscription
    for subscription in expired_subscriptions_empty:
        logger.debug(
            '%2d: buy_date=%s, max_lesson_date=%s, classes__timeline count=%s, last_send=%s',
            subscription.id,
            subscription.buy_date,
            subscription.max_lesson_date,
            subscription.classes.filter(timeline__start__isnull=False).count(),
            subscription.when_waste_money_notification_sent or '-'
        )
        owl = Owl(
            template='mail/wasted_money_notification.html',
            ctx={
                'subscription': subscription,
                'is_repeat': subscription.when_waste_money_notification_sent is not None,
            },
            to=[subscription.customer.user.email],
            timezone=subscription.customer.timezone,
        )
        owl.send()

        subscription.when_waste_money_notification_sent = timezone.now().isoformat()
        subscription.save()
