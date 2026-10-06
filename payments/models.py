from django.db import models


class Payment(models.Model):
    """
    Libro de transacciones de pago (una fila por intento de pago).

    Un reintento tras un rechazo crea un Payment nuevo con otra referencia,
    igual que en Wompi (la referencia de una transacción es única).
    """
    STATUS_PENDING = 'PENDING'
    STATUS_APPROVED = 'APPROVED'
    STATUS_DECLINED = 'DECLINED'
    STATUS_ERROR = 'ERROR'
    STATUS_VOIDED = 'VOIDED'

    STATUSES = (
        (STATUS_PENDING, 'Pendiente'),
        (STATUS_APPROVED, 'Aprobado'),
        (STATUS_DECLINED, 'Rechazado'),
        (STATUS_ERROR, 'Error'),
        (STATUS_VOIDED, 'Anulado'),
    )

    # Transiciones válidas. Los estados finales de Wompi no cambian, salvo
    # la reversión de un pago aprobado (módulo de reclamaciones, Sprint 6).
    ALLOWED_TRANSITIONS = {
        STATUS_PENDING: {STATUS_APPROVED, STATUS_DECLINED, STATUS_ERROR},
        STATUS_APPROVED: {STATUS_VOIDED},
        STATUS_DECLINED: set(),
        STATUS_ERROR: set(),
        STATUS_VOIDED: set(),
    }

    GATEWAY_MOCK = 'mock'
    GATEWAY_WOMPI = 'wompi'

    GATEWAYS = (
        (GATEWAY_MOCK, 'Simulada'),
        (GATEWAY_WOMPI, 'Wompi'),
    )

    reference = models.CharField(max_length=64, unique=True, verbose_name='Referencia')
    service_request_id = models.CharField(max_length=255, db_index=True, verbose_name='ID de la Solicitud')
    client_uid = models.CharField(max_length=128, db_index=True, verbose_name='UID del Cliente')
    worker_uid = models.CharField(max_length=128, db_index=True, verbose_name='UID del Trabajador')
    # Montos siempre en centavos (enteros), nunca floats
    amount_in_cents = models.PositiveBigIntegerField(verbose_name='Monto (centavos)')
    # Comisión de ADS: aún sin definir, por ahora siempre 0
    commission_in_cents = models.PositiveBigIntegerField(default=0, verbose_name='Comisión (centavos)')
    currency = models.CharField(max_length=3, default='COP', verbose_name='Moneda')
    status = models.CharField(max_length=10, choices=STATUSES, default=STATUS_PENDING, db_index=True, verbose_name='Estado')
    gateway = models.CharField(max_length=10, choices=GATEWAYS, verbose_name='Pasarela')
    gateway_transaction_id = models.CharField(max_length=100, blank=True, default='', db_index=True, verbose_name='ID de Transacción en la Pasarela')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de Creación')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Última Actualización')

    class Meta:
        verbose_name = 'Pago'
        verbose_name_plural = 'Pagos'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reference} - {self.status} - {self.amount_in_cents}"

    def can_transition_to(self, new_status):
        return new_status in self.ALLOWED_TRANSITIONS.get(self.status, set())


class PaymentEvent(models.Model):
    """
    Evento recibido de la pasarela (webhook). Sirve de auditoría e idempotencia.

    Se guardan también los eventos con checksum inválido o con referencia
    desconocida (payment = null) para poder auditarlos.
    """
    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='events',
        verbose_name='Pago',
    )
    event_type = models.CharField(max_length=50, verbose_name='Tipo de Evento')
    payload = models.JSONField(verbose_name='Payload')
    checksum = models.CharField(max_length=64, blank=True, default='', db_index=True, verbose_name='Checksum')
    checksum_valid = models.BooleanField(default=False, verbose_name='Checksum Válido')
    received_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de Recepción')

    class Meta:
        verbose_name = 'Evento de Pago'
        verbose_name_plural = 'Eventos de Pago'
        ordering = ['-received_at']

    def __str__(self):
        return f"{self.event_type} - {self.payment_id} - {self.received_at}"
