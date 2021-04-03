from datetime import timedelta

from django.conf import settings
from django.core import mail
from freezegun import freeze_time

from elk.utils.testing import TestCase, create_customer, create_teacher
from market.models import Subscription
from market.tasks import notify_waste_money
from products.models import Product1


@freeze_time('2032-09-10 15:46')
class TestWasteMoneyNotificationEmail(TestCase):
    fixtures = ('products', 'lessons')

    @classmethod
    def setUpTestData(cls):
        cls.product = Product1.objects.get(pk=1)
        cls.product.duration = timedelta(days=25)
        cls.product.save()

        cls.teacher = create_teacher(works_24x7=True)

        cls.customer = create_customer()

        cls.subscription: Subscription = Subscription(
            customer=cls.customer,
            product=cls.product,
            buy_price=150,
        )

        cls.subscription.save()

    def _schedule(self, c, date=None):
        if date is None:
            date = self.tzdatetime(2032, 9, 11, 11, 30)

        c.schedule(
            teacher=self.teacher,
            date=date,
            allow_besides_working_hours=True,
        )
        c.save()
        self.assertTrue(c.is_scheduled)
        return c

    def test_no_notify_early_no_classes(self):
        # action:
        # wait a day (other time less than settings.WASTE_MONEY_NOTIFY_FIRST_DELAY_DAYS)
        with freeze_time('2032-09-13 15:46'):
            notify_waste_money()
        # assert:
        # nothing changed - no notification, last notification time not changed

        self.subscription.refresh_from_db()

        self.assertEqual(len(mail.outbox), 0)
        self.assertIsNone(self.subscription.when_waste_money_notification_sent)

    def test_no_notify_early_has_classes(self):
        # assume
        lesson1, lesson2 = self.subscription.classes.all()[:2]
        self._schedule(lesson1, self.tzdatetime(2032, 9, 12, 12, 0))
        self._schedule(lesson2, self.tzdatetime(2032, 9, 14, 12, 0))
        mail.outbox = []  # reset mailbox from schedule notification

        # action:
        # wait a day (other time)
        # do task of generation of notification
        with freeze_time(
            '2032-09-19 15:46'):  # less than last week after last lesson and more than week from first lesson
            notify_waste_money()

        self.subscription.refresh_from_db()
        # assert:
        # nothing changed - no notification, last notification time not changed

        self.assertEqual(len(mail.outbox), 0)
        self.assertIsNone(self.subscription.when_waste_money_notification_sent)

    def test_notify_from_last_lesson(self):
        # assume
        lesson1, lesson2 = self.subscription.classes.all()[:2]
        last_lesson_time = self.tzdatetime(2032, 9, 12, 12, 0)
        self._schedule(lesson1)
        self._schedule(lesson2, last_lesson_time)
        mail.outbox = []  # reset mailbox from schedule notification

        # action:
        # wait a week and 2 hour (other time > )
        # do task of generation of notification
        new_time = last_lesson_time + timedelta(
            days=settings.WASTE_MONEY_NOTIFY_FIRST_DELAY_DAYS,
            hours=2
        )
        with freeze_time(new_time):
            # run this few times to check for repetitive emails — all notifications should be sent one time
            for _ in range(5):
                notify_waste_money()

        self.subscription.refresh_from_db()
        # assert:
        # no notification sent, last notification time changed
        self.assertIsNotNone(self.subscription.when_waste_money_notification_sent)
        self.assertEqual(len(mail.outbox), 1)

    def test_notify_when_no_lessons(self):
        last_lesson_time = self.subscription.buy_date

        # action:
        # wait a week and 2 hour (other time > a week)
        # do task of generation of notification
        new_time = last_lesson_time + timedelta(
            days=settings.WASTE_MONEY_NOTIFY_FIRST_DELAY_DAYS,
            hours=2
        )
        with freeze_time(new_time):
            # run this few times to check for repetitive emails — all notifications should be sent one time
            for _ in range(5):
                notify_waste_money()

        self.subscription.refresh_from_db()
        # assert:
        # notification sent, last notification time setted
        self.assertIsNotNone(self.subscription.when_waste_money_notification_sent)
        self.assertEqual(len(mail.outbox), 1)

    def test_dont_repeat_notification_less_than_day(self):
        last_lesson_time = self.subscription.buy_date
        when_waste_money_notification_sent = last_lesson_time + timedelta(
            days=settings.WASTE_MONEY_NOTIFY_FIRST_DELAY_DAYS,
            hours=2
        )
        self.subscription.when_waste_money_notification_sent = when_waste_money_notification_sent.isoformat()
        self.subscription.save()
        new_time = when_waste_money_notification_sent + timedelta(days=settings.WASTE_MONEY_NOTIFY_NEXT_DELAY_DAYS,
                                                                  hours=-3)
        # action:
        # wait a week and 2 hour (other time > a week)
        # do task of generation of notification
        with freeze_time(new_time):
            # run this few times to check for repetitive emails — all notifications should be sent one time
            for _ in range(5):
                notify_waste_money()

        self.subscription.refresh_from_db()
        # assert:
        # no notification sent, last notification time not changed
        self.assertEqual(
            self.subscription.when_waste_money_notification_sent.isoformat(),
            when_waste_money_notification_sent.isoformat()
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_repeat_notification_next_day(self):
        last_lesson_time = self.subscription.buy_date
        when_waste_money_notification_sent = last_lesson_time + timedelta(
            days=settings.WASTE_MONEY_NOTIFY_FIRST_DELAY_DAYS,
            hours=2
        )
        self.subscription.when_waste_money_notification_sent = when_waste_money_notification_sent.isoformat()
        self.subscription.save()

        new_time = when_waste_money_notification_sent + timedelta(days=settings.WASTE_MONEY_NOTIFY_NEXT_DELAY_DAYS,
                                                                  hours=1)
        # action:
        # wait a week and 2 hour (other time > a week)
        # do task of generation of notification
        with freeze_time(new_time.isoformat()):
            # run this few times to check for repetitive emails — all notifications should be sent one time
            for _ in range(5):
                notify_waste_money()

        self.subscription.refresh_from_db()
        # assert:
        # new notification sent
        self.assertEqual(len(mail.outbox), 1)
