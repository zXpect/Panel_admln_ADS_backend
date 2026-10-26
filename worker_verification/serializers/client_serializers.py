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
    isActive = serializers.SerializerMethodField()

    def get_isActive(self, client):
        # Cuenta habilitada (HU-32); sin el campo cuenta como activa
        return client.get('isActive') is not False


class ClientListSerializer(serializers.Serializer):
    """
    Serializer simplificado para listados de clientes (tolerante a campos faltantes)
    """
    id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)
    lastName = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    # Para la tabla del panel
    phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    timestamp = serializers.IntegerField(required=False, allow_null=True)
    isActive = serializers.SerializerMethodField()

    def get_isActive(self, client):
        return client.get('isActive') is not False
