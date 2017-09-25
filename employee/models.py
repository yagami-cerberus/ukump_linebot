
from django.contrib.postgres.fields import ArrayField, JSONField
from django.db.models.functions import Now
from django.db import models


class Profile(models.Model):
    class Meta:
        db_table = "employee"

    def __str__(self):
        return "%i#員工 %s" % (self.id, self.name)

    def __repr__(self):
        return "<Employee %i: %s>" % (self.id, self.name)

    name = models.TextField()
    profile = JSONField(null=True)
    members = ArrayField(models.TextField())
    created_at = models.DateTimeField(auto_now_add=True)

    def today_nursing_schedule(self):
        return self.nursing_schedule.extra(where=(
            "(LOWER(schedule) AT TIME ZONE 'Asia/Taipei')::Date = (current_timestamp AT TIME ZONE 'Asia/Taipei')::Date",))

    @classmethod
    def get_id_from_line_id(cls, line_id):
        return LineBotIntegration.objects.filter(lineid=line_id).values_list('employee_id', flat=True).first()


class LineBotIntegration(models.Model):
    class Meta:
        db_table = "employee_linebot_integration"

    def __repr__(self):
        return "<Employee '%s' LineId '%s'>" % (self.employee.name, self.lineid)

    lineid = models.TextField(primary_key=True)
    employee = models.ForeignKey(Profile)


class LineMessageManager(models.Manager):
    def padding_message(self):
        return self.get_queryset().filter(scheduled_at__lt=Now())


class LineMessageQueue(models.Model):
    class Meta:
        db_table = "employee_line_message_queue"

    @classmethod
    def pack_text_message(cls, message):
        return {"M": "t", "t": message}

    objects = LineMessageManager()

    employee = models.ForeignKey(Profile)
    message = models.TextField()
    """
    {
        "T": "ECARE",
        "M": "t"|"q"|"i"|"u",
        "t": "text message"|"question title",
        "q": [["LABEL1", value], ["LABEL2", value...]]
        "u": [["LABEL1", url1], ["LABEL2", url2...]]
    }
    """
    scheduled_at = models.DateTimeField()
    queue_index = models.IntegerField(default=1)

    def get_line_ids(self):
        return self.employee.linebotintegration_set.values_list('lineid', flat=True)
