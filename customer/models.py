
from django.contrib.postgres.fields import JSONField
from django.db.models.functions import Now
from django.db import models
import json


class LineMessageManager(models.Manager):
    def padding_message(self):
        return self.get_queryset().filter(scheduled_at__lt=Now())


class Profile(models.Model):
    class Meta:
        db_table = "customer"

    name = models.TextField()
    phone = models.TextField(null=True, blank=True)
    profile = JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "%s#客戶 %s" % (self.id, self.name)

    def push_raw_message(self, raw_data, scheduled_at=Now()):
        LineMessageQueue(customer=self, scheduled_at=scheduled_at, message=raw_data).save()

    def push_message(self, message, scheduled_at=Now()):
        LineMessageQueue(customer=self, scheduled_at=scheduled_at, message=json.dumps({'M': 't', 'text': message})).save()


class LineBotIntegration(models.Model):
    class Meta:
        db_table = "customer_linebot_integration"

    lineid = models.TextField(primary_key=True)
    customer = models.ForeignKey(Profile, on_delete=models.CASCADE)


class LineMessageQueue(models.Model):
    class Meta:
        db_table = "customer_message_queue"

    objects = LineMessageManager()

    customer = models.ForeignKey(Profile, on_delete=models.CASCADE)
    scheduled_at = models.DateTimeField()
    message = models.TextField()

    def get_line_ids(self):
        return self.customer.linebotintegration_set.values_list('lineid', flat=True)
