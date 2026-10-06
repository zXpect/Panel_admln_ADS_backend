from django.contrib import admin

from .models import Payment, PaymentEvent


class PaymentEventInline(admin.TabularInline):
    model = PaymentEvent
    extra = 0
    can_delete = False
    readonly_fields = ('event_type', 'checksum_valid', 'checksum', 'payload', 'received_at')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('reference', 'service_request_id', 'amount_in_cents', 'status', 'gateway', 'created_at')
    list_filter = ('status', 'gateway')
    search_fields = ('reference', 'service_request_id', 'client_uid', 'worker_uid', 'gateway_transaction_id')
    inlines = [PaymentEventInline]

    # Solo lectura: el estado solo cambia por eventos de la pasarela
    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'payment', 'checksum_valid', 'received_at')
    list_filter = ('event_type', 'checksum_valid')

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
