import re

from rest_framework import serializers

from pricing.services.worker_categories import as_list


class WorkerCreateSerializer(serializers.Serializer):
    """
    Serializer específico para creación de trabajadores individuales
    El ID se genera automáticamente en el backend desde Firebase Auth
    """
    name = serializers.CharField(max_length=100, required=True)
    lastName = serializers.CharField(max_length=100, required=True)
    email = serializers.EmailField(required=True)
    work = serializers.CharField(max_length=100, required=True)
    phone = serializers.CharField(max_length=20, required=True)
    description = serializers.CharField(required=False, allow_blank=True)
    latitude = serializers.FloatField(required=False, default=0.0)
    longitude = serializers.FloatField(required=False, default=0.0)
    pricePerHour = serializers.FloatField(required=False, default=0.0)
    experience = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(required=False, min_length=6, allow_blank=True)

    def validate_email(self, value):
        """Valida y normaliza el email"""
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', value):
            raise serializers.ValidationError("Formato de email inválido")
        return value.lower().strip()

    def validate_phone(self, value):
        """Valida que el teléfono tenga formato correcto"""
        phone = re.sub(r'\D', '', value)
        if len(phone) < 7 or len(phone) > 15:
            raise serializers.ValidationError("Número de teléfono inválido (debe tener entre 7 y 15 dígitos)")
        return phone

    def validate_pricePerHour(self, value):
        """Valida que el precio sea positivo"""
        if value < 0:
            raise serializers.ValidationError("El precio debe ser positivo")
        return value

    def validate_latitude(self, value):
        """Valida que la latitud esté en rango válido"""
        if value < -90 or value > 90:
            raise serializers.ValidationError("Latitud debe estar entre -90 y 90")
        return value

    def validate_longitude(self, value):
        """Valida que la longitud esté en rango válido"""
        if value < -180 or value > 180:
            raise serializers.ValidationError("Longitud debe estar entre -180 y 180")
        return value


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
    # Cuenta habilitada (HU-32); sin el campo cuenta como activa. Solo lectura:
    # se cambia con PATCH /api/admin/accounts/{uid}/status/
    isActive = serializers.SerializerMethodField()
    # Para la tabla del panel: oficios del catálogo (D16) y estado de verificación.
    # Solo lectura: los cambian la app y las rutas de verificación
    categories = serializers.SerializerMethodField()
    verificationStatus = serializers.SerializerMethodField()

    def get_isActive(self, worker):
        return worker.get('isActive') is not False

    def get_categories(self, worker):
        return [slug for slug in as_list(worker.get('categories')) if isinstance(slug, str)]

    def get_verificationStatus(self, worker):
        status = worker.get('verificationStatus')
        return status if isinstance(status, dict) else None

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