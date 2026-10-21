from django.contrib import admin

from worker_verification.models import SystemConfig

from .models import ConfigAuditLog, ServiceCategory, Task
from .services.config_audit_service import config_audit_service


class AuditedAdmin(admin.ModelAdmin):
    """
    Cada alta o cambio queda en ConfigAuditLog con el administrador autenticado.
    El admin de Django ya envuelve save_model en una transacción, así que el
    cambio y su registro se guardan juntos. No se borra: se desactiva.
    """

    def save_model(self, request, obj, form, change):
        old = type(obj).objects.get(pk=obj.pk) if change else None
        super().save_model(request, obj, form, change)
        config_audit_service.log_change(request.user, old, obj)

    def has_delete_permission(self, request, obj=None):
        return False


class TaskInline(admin.TabularInline):
    model = Task
    extra = 0
    fields = ('slug', 'name', 'unit', 'reference_min_cop', 'reference_max_cop', 'is_active', 'order')
    show_change_link = True
    can_delete = False

    # Las tareas se editan en su propio formulario para que el cambio quede auditado
    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(AuditedAdmin):
    list_display = ('name', 'slug', 'is_active', 'order')
    list_filter = ('is_active',)
    inlines = [TaskInline]


@admin.register(Task)
class TaskAdmin(AuditedAdmin):
    list_display = ('name', 'category', 'unit', 'reference_min_cop', 'reference_max_cop', 'is_active', 'order')
    list_filter = ('category', 'unit', 'is_active')
    search_fields = ('name', 'slug')


# SystemConfig vive en worker_verification, pero sus cambios se auditan como
# los del catálogo (I10), así que se registra aquí.
@admin.register(SystemConfig)
class SystemConfigAdmin(AuditedAdmin):
    list_display = ('key', 'value', 'updated_at')
    search_fields = ('key',)

    def get_readonly_fields(self, request, obj=None):
        return ('key',) if obj else ()


@admin.register(ConfigAuditLog)
class ConfigAuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'admin', 'entity', 'entity_key')
    list_filter = ('entity',)
    search_fields = ('entity_key',)
    readonly_fields = ('admin', 'entity', 'entity_key', 'old_value', 'new_value', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
