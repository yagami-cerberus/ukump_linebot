from django.contrib import admin


class LineMessageQueueAdmin(admin.ModelAdmin):
    def get_list_display(self, request):
        if hasattr(self.model, "employee"):
            return ('id', 'employee', 'scheduled_at')
        elif hasattr(self.model, "customer"):
            return ('id', 'customer', 'scheduled_at')
