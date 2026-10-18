from django.contrib import admin

from .models import PQR


@admin.register(PQR)
class PQRAdmin(admin.ModelAdmin):
    """Consulta en el admin de Django; se responden desde el panel (PATCH /api/pqr/<id>/)."""
    list_display = ('id', 'type', 'status', 'author_role', 'service_request_id', 'created_at', 'due_at')
    list_filter = ('status', 'type', 'author_role')
    search_fields = ('service_request_id', 'author_uid')
    readonly_fields = [field.name for field in PQR._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
