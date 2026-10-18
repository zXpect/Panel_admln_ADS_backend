import time

from rest_framework import serializers

from pricing.serializers import EstimateSerializer


class StrictIntegerField(serializers.IntegerField):
    """Entero estricto: rechaza 50000.5, "50000", true. El dinero nunca es float."""

    def to_internal_value(self, data):
        if not isinstance(data, int) or isinstance(data, bool):
            raise serializers.ValidationError('Debe ser un número entero')
        return super().to_internal_value(data)


class ServiceRequestCreateSerializer(EstimateSerializer):
    """
    Cuerpo de POST /api/requests/: los ítems y el oficio se validan como en el
    estimado; el trabajador se valida contra Firebase en el servicio.
    """
    worker_id = serializers.CharField(max_length=255)
    address = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True, default='')
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)
    # Medición del tiempo de búsqueda (Sprint 6); opcionales
    search_started_at = StrictIntegerField(min_value=0, required=False)
    worker_selected_at = StrictIntegerField(min_value=0, required=False)

    def validate_worker_id(self, value):
        if any(char in value for char in '/.#$[]'):
            raise serializers.ValidationError('ID de trabajador inválido')
        return value


def _now_ms():
    return int(time.time() * 1000)


# Motivos del ajuste de la cotización (D5) y de la cancelación (D8)
ADJUSTMENT_REASONS = ('materiales', 'dificultad', 'tiempo', 'condiciones_lugar', 'otro')
CANCELLATION_REASONS = {
    'client': ('ya_no_lo_necesito', 'encontre_otra_opcion', 'precio', 'horario', 'otro'),
    'worker': ('no_disponible', 'fuera_de_zona', 'trabajo_no_corresponde', 'otro'),
}
OTHER_REASON = 'otro'
MAX_REASON_TEXT = 300


def require_text_with_other(code, text, text_field):
    """El texto del motivo es obligatorio solo con «otro» (D5, D8)."""
    if code == OTHER_REASON and not text:
        raise serializers.ValidationError({text_field: ['Describe el motivo cuando eliges «otro»']})


class ScheduleSerializer(serializers.Serializer):
    """Agenda del servicio (D9): llegada futura, dentro de 30 días, y duración estimada."""
    MAX_DAYS_AHEAD = 30

    scheduled_at = StrictIntegerField(help_text='Fecha y hora de llegada (ms desde 1970, UTC)')
    estimated_duration_min = StrictIntegerField(min_value=15, max_value=720)

    def validate_scheduled_at(self, value):
        now = _now_ms()
        if value <= now:
            raise serializers.ValidationError('La fecha y hora de llegada debe ser futura')
        if value > now + self.MAX_DAYS_AHEAD * 24 * 60 * 60 * 1000:
            raise serializers.ValidationError(f'La fecha de llegada debe estar dentro de los próximos {self.MAX_DAYS_AHEAD} días')
        return value


class QuoteSubmitSerializer(ScheduleSerializer):
    """
    Cotización del trabajador. Si el motivo hace falta (precio ajustado) lo
    decide el servicio con el quote_reference congelado de la solicitud.
    """
    quoted_price = StrictIntegerField(min_value=1, help_text='Precio en pesos COP (entero)')
    adjustment_reason_code = serializers.ChoiceField(
        choices=ADJUSTMENT_REASONS, required=False, allow_blank=True, default='')
    adjustment_reason_text = serializers.CharField(
        max_length=MAX_REASON_TEXT, required=False, allow_blank=True, default='')

    def validate(self, attrs):
        require_text_with_other(attrs['adjustment_reason_code'], attrs['adjustment_reason_text'],
                                'adjustment_reason_text')
        return attrs


class CancelSerializer(serializers.Serializer):
    """Motivo de la cancelación; si el código vale para el rol lo valida el servicio."""
    reason_code = serializers.ChoiceField(choices=sorted({code for codes in CANCELLATION_REASONS.values()
                                                          for code in codes}))
    reason_text = serializers.CharField(max_length=MAX_REASON_TEXT, required=False, allow_blank=True, default='')

    def validate(self, attrs):
        require_text_with_other(attrs['reason_code'], attrs['reason_text'], 'reason_text')
        return attrs


class QuoteRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')


class RatingSerializer(serializers.Serializer):
    rating = StrictIntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')


class NotificationSerializer(serializers.Serializer):
    """Eventos de la app que generan una notificación al otro participante."""
    TYPES = ('new_request', 'request_accepted', 'request_rejected', 'status_change')

    request_id = serializers.CharField(max_length=255)
    type = serializers.ChoiceField(choices=TYPES)

    def validate_request_id(self, value):
        if any(char in value for char in '/.#$[]'):
            raise serializers.ValidationError('ID de solicitud inválido')
        return value
