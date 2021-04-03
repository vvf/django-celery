from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import ugettext_lazy as _


class EventManager(models.Manager):
    def by_originator(self, originator):
        return self.get_queryset() \
            .filter(originator_id=originator.pk) \
            .filter(originator_type=ContentType.objects.get_for_model(originator))


class Event(models.Model):
    """
    Single accounting event record. Accounting event is everything, that affects
    teacher payments.
    """
    EVENT_TYPES = (
        ('class', _('Completed class')),
        ('customer_inspired_cancellation', _('Customer inspired cancellation')),
    )

    objects = EventManager()

    teacher = models.ForeignKey('teachers.Teacher', related_name='accounting_events')
    event_type = models.CharField(max_length=140, choices=EVENT_TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)

    originator_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    originator_id = models.PositiveIntegerField()
    originator = GenericForeignKey('originator_type', 'originator_id')

    def __str__(self):
        return '%s: %s' % (self.teacher, self.event_type)

    @property
    def originator_time(self):
        if self.event_type == 'class':
            return self.originator.start

        if self.event_type == 'customer_inspired_cancellation':  # accounting record appears exactly when user cancells a class
            return self.timestamp

    @property
    def originator_customers(self):
        if self.event_type == 'class':
            return list(i.customer for i in self.originator.classes.all())

        if self.event_type == 'customer_inspired_cancellation':
            return [self.originator.customer]
