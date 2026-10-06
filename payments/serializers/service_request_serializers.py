from rest_framework import serializers


class StrictIntegerField(serializers.IntegerField):
    """Entero estricto: rechaza 50000.5, "50000", true. El dinero nunca es float."""

    def to_internal_value(self, data):
        if not isinstance(data, int) or isinstance(data, bool):
            raise serializers.ValidationError('Debe ser un número entero')
        return super().to_internal_value(data)


class QuoteSubmitSerializer(serializers.Serializer):
    quoted_price = StrictIntegerField(min_value=1, help_text='Precio en pesos COP (entero)')


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
