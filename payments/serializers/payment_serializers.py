from urllib.parse import urlparse

from rest_framework import serializers

from ..models import Payment, PaymentEvent

# La app vuelve del checkout por deep link; no se permite redirigir a otros sitios
ALLOWED_REDIRECT_SCHEMES = ('adsapp',)
DEFAULT_REDIRECT_URL = 'adsapp://payment-result'


class PaymentCreateSerializer(serializers.Serializer):
    """
    Entrada de POST /api/payments/. Solo se recibe la solicitud: el monto lo
    calcula el servidor a partir de la cotización aceptada.
    """
    service_request_id = serializers.CharField(max_length=255)
    redirect_url = serializers.CharField(max_length=500, required=False, default=DEFAULT_REDIRECT_URL)

    def validate_service_request_id(self, value):
        # Claves de Firebase: sin '/', '.', '#', '$', '[' ni ']'
        if any(char in value for char in '/.#$[]'):
            raise serializers.ValidationError('ID de solicitud inválido')
        return value

    def validate_redirect_url(self, value):
        if urlparse(value).scheme not in ALLOWED_REDIRECT_SCHEMES:
            raise serializers.ValidationError('redirect_url debe ser un deep link de la app (adsapp://)')
        return value

    def to_internal_value(self, data):
        # Cualquier campo de monto enviado por la app se ignora explícitamente
        if hasattr(data, 'copy'):
            data = data.copy()
            for key in ('amount', 'amount_in_cents', 'price', 'quoted_price'):
                data.pop(key, None)
        return super().to_internal_value(data)


class PaymentSerializer(serializers.ModelSerializer):
    """Vista de un pago para la app (cliente o trabajador)."""
    amount_cop = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = (
            'reference', 'service_request_id', 'amount_in_cents', 'amount_cop',
            'currency', 'status', 'created_at', 'updated_at',
        )

    def get_amount_cop(self, obj):
        return obj.amount_in_cents // 100


class PaymentEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentEvent
        fields = ('id', 'event_type', 'checksum_valid', 'payload', 'received_at')


class PaymentAdminSerializer(PaymentSerializer):
    """Vista completa para el panel admin, con el historial de eventos."""
    events = PaymentEventSerializer(many=True, read_only=True)

    class Meta(PaymentSerializer.Meta):
        fields = PaymentSerializer.Meta.fields + (
            'id', 'client_uid', 'worker_uid', 'commission_in_cents',
            'gateway', 'gateway_transaction_id', 'events',
        )


class PaymentAdminListSerializer(PaymentSerializer):
    class Meta(PaymentSerializer.Meta):
        fields = PaymentSerializer.Meta.fields + (
            'id', 'client_uid', 'worker_uid', 'commission_in_cents', 'gateway',
        )
