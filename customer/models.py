
from django.contrib.postgres.fields import JSONField
from django.db.models.functions import Now
from django.db import models


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
        return "%i#客戶 %s" % (self.id, self.name)

    @classmethod
    def get_id_from_line_id(cls, line_id):
        return LineBotIntegration.objects.filter(lineid=line_id).values_list('customer_id', flat=True).first()


class LineBotIntegration(models.Model):
    class Meta:
        db_table = "customer_linebot_integration"

    lineid = models.TextField(primary_key=True)
    customer = models.ForeignKey(Profile)


class LineMessageQueue(models.Model):
    class Meta:
        db_table = "customer_message_queue"

    objects = LineMessageManager()

    customer = models.ForeignKey(Profile)
    scheduled_at = models.DateTimeField()
    message = JSONField()

    def get_line_ids(self):
        return self.customer.linebotintegration_set.values_list('lineid', flat=True)
