import re

from rest_framework import serializers

from pricing.services.worker_categories import as_list, resolve_worker_categories


class CategoriesMixin:
    """
    `categories` como en el registro de la app (D16): slugs del catálogo, hasta
    `worker_max_categories`. También se escribe `work` con el primer oficio,
    el respaldo que leen las versiones viejas de la app.
    """

    def validate_categories(self, value):
        try:
            slugs, self._work = resolve_worker_categories(value)
        except ValueError as error:
            raise serializers.ValidationError(str(error))
        return slugs

    def validate(self, attrs):
        if 'categories' in attrs:
            attrs['work'] = self._work
        return attrs


class WorkerCreateSerializer(CategoriesMixin, serializers.Serializer):
    """
    Serializer específico para creación de trabajadores individuales
    El ID se genera automáticamente en el backend desde Firebase Auth.
    Sin precio por hora (los precios salen del catálogo y la cotización) ni
    ubicación (la escribe la app al conectarse).
    """
    name = serializers.CharField(max_length=100, required=True)
    lastName = serializers.CharField(max_length=100, required=True)
    email = serializers.EmailField(required=True)
    categories = serializers.ListField(child=serializers.CharField(max_length=60), required=True)
    phone = serializers.CharField(max_length=20, required=True)
    description = serializers.CharField(required=False, allow_blank=True)
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


class WorkerSerializer(serializers.Serializer):
    """Salida del trabajador para el panel (las escrituras usan WorkerUpdateSerializer)."""
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


class WorkerUpdateSerializer(CategoriesMixin, serializers.Serializer):
    """
    Serializer para actualizar trabajadores (PUT y PATCH; solo se escriben los
    campos enviados). La calificación la escribe el servidor y la ubicación la
    app (o PATCH .../location/), así que aquí no se aceptan.
    """
    name = serializers.CharField(max_length=100, required=False)
    lastName = serializers.CharField(max_length=100, required=False)
    email = serializers.EmailField(required=False)
    categories = serializers.ListField(child=serializers.CharField(max_length=60), required=False)
    isAvailable = serializers.BooleanField(required=False)
    isOnline = serializers.BooleanField(required=False)
    image = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
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