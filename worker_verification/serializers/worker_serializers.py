from rest_framework import serializers


class WorkerSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    lastName = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    work = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    fcmToken = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    isAvailable = serializers.BooleanField(default=True)
    isOnline = serializers.BooleanField(default=False)
    image = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    latitude = serializers.FloatField(required=False, default=0.0)
    longitude = serializers.FloatField(required=False, default=0.0)
    rating = serializers.FloatField(required=False, default=0.0)
    totalRatings = serializers.IntegerField(required=False, default=0)
    pricePerHour = serializers.FloatField(required=False, default=0.0)
    experience = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    timestamp = serializers.IntegerField(required=False, allow_null=True)

    def validate_rating(self, value):
        """Valida que el rating esté entre 0 y 5"""
        if value < 0 or value > 5:
            raise serializers.ValidationError("Rating debe estar entre 0 y 5")
        return value
    
    def validate_pricePerHour(self, value):
        """Valida que el precio sea positivo"""
        if value < 0:
            raise serializers.ValidationError("El precio debe ser positivo")
        return value


class WorkerUpdateSerializer(serializers.Serializer):
    """
    Serializer para actualizar trabajadores (campos opcionales)
    """
    name = serializers.CharField(max_length=100, required=False)
    lastName = serializers.CharField(max_length=100, required=False)
    email = serializers.EmailField(required=False)
    work = serializers.CharField(max_length=100, required=False)
    isAvailable = serializers.BooleanField(required=False)
    isOnline = serializers.BooleanField(required=False)
    image = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    latitude = serializers.FloatField(required=False)
    longitude = serializers.FloatField(required=False)
    pricePerHour = serializers.FloatField(required=False)
    experience = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class WorkerAvailabilitySerializer(serializers.Serializer):
    """
    Serializer para actualizar disponibilidad
    """
    isAvailable = serializers.BooleanField(required=True)


class WorkerOnlineStatusSerializer(serializers.Serializer):
    """
    Serializer para actualizar estado en línea
    """
    isOnline = serializers.BooleanField(required=True)


class WorkerVerificationStatusSerializer(serializers.Serializer):
    """
    Serializer para actualizar SOLO el estado de verificación.
    `submittedAt` se conserva pero es de solo lectura.
    """
    status = serializers.ChoiceField(
        choices=["documents_submitted", "approved", "rejected"],
        required=True
    )
    submittedAt = serializers.IntegerField(read_only=True)
    



class WorkerLocationSerializer(serializers.Serializer):
    """
    Serializer para actualizar ubicación
    """
    latitude = serializers.FloatField(required=True)
    longitude = serializers.FloatField(required=True)


class WorkerRatingSerializer(serializers.Serializer):
    """
    Serializer para agregar una calificación
    """
    rating = serializers.FloatField(required=True, min_value=1.0, max_value=5.0)
    
    def validate_rating(self, value):
        """Valida que el rating esté entre 1 y 5"""
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating debe estar entre 1 y 5")
        return value


class WorkerStatisticsSerializer(serializers.Serializer):
    """
    Serializer para estadísticas de trabajadores
    """
    total = serializers.IntegerField()
    available = serializers.IntegerField()
    online = serializers.IntegerField()
    by_category = serializers.DictField(child=serializers.IntegerField())