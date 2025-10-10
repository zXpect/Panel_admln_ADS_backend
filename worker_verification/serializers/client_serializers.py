from rest_framework import serializers


class ClientSerializer(serializers.Serializer):
    """
    Serializer para clientes
    """
    id = serializers.CharField(read_only=True)
    name = serializers.CharField(max_length=100)
    lastName = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    
    # Campos adicionales opcionales
    phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    image = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    timestamp = serializers.IntegerField(required=False)


class ClientListSerializer(serializers.Serializer):
    """
    Serializer simplificado para listados de clientes (tolerante a campos faltantes)
    """
    id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)
    lastName = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)