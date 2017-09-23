
from django.contrib.postgres.fields import JSONField
from django.db import models


class Profile(models.Model):
    class Meta:
        db_table = "customer"

    name = models.TextField()
    phone = models.TextField(null=True)
    profile = JSONField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def get_id_from_line_id(cls, line_id):
        return LineBotIntegration.objects.filter(lineid=line_id).values_list('customer_id', flat=True).first()


class MessageQueue(models.Model):
    class Meta:
        db_table = "customer_message_queue"

    customer = models.ForeignKey(Profile)
    scheduled_at = models.DateTimeField()
    message = JSONField()


class LineBotIntegration(models.Model):
    class Meta:
        db_table = "customer_linebot_integration"

    lineid = models.TextField(primary_key=True)
    customer = models.ForeignKey(Profile)
