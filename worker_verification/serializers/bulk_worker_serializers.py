from rest_framework import serializers
import re


class BulkWorkerUploadSerializer(serializers.Serializer):
    """
    Serializer para validar datos de un trabajador en carga masiva
    """
    # Campos obligatorios
    name = serializers.CharField(max_length=100, required=True)
    lastName = serializers.CharField(max_length=100, required=True)
    email = serializers.EmailField(required=True)
    work = serializers.CharField(max_length=100, required=True)
    phone = serializers.CharField(max_length=20, required=True)
    
    # Campos opcionales
    description = serializers.CharField(required=False, allow_blank=True, default='')
    latitude = serializers.FloatField(required=False, default=0.0)
    longitude = serializers.FloatField(required=False, default=0.0)
    pricePerHour = serializers.FloatField(required=False, default=0.0)
    experience = serializers.CharField(required=False, allow_blank=True, default='')
    
    # Campo para contraseña temporal (opcional en Excel)
    password = serializers.CharField(
        required=False, 
        allow_blank=True,
        min_length=6,
        help_text="Si no se proporciona, se generará automáticamente"
    )
    
    def validate_email(self, value):
        """Valida formato de email"""
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', value):
            raise serializers.ValidationError("Formato de email inválido")
        return value.lower().strip()
    
    def validate_phone(self, value):
        """Valida formato de teléfono"""
        phone = re.sub(r'\D', '', value)  # Remover caracteres no numéricos
        if len(phone) < 7 or len(phone) > 15:
            raise serializers.ValidationError("Número de teléfono inválido")
        return phone
    
    def validate_work(self, value):
        """Valida que la categoría de trabajo no esté vacía"""
        if not value or not value.strip():
            raise serializers.ValidationError("La categoría de trabajo es obligatoria")
        return value.strip()
    
    def validate_pricePerHour(self, value):
        """Valida que el precio sea positivo"""
        if value < 0:
            raise serializers.ValidationError("El precio debe ser positivo")
        return value
    
    def validate_latitude(self, value):
        """Valida rango de latitud"""
        if value < -90 or value > 90:
            raise serializers.ValidationError("Latitud debe estar entre -90 y 90")
        return value
    
    def validate_longitude(self, value):
        """Valida rango de longitud"""
        if value < -180 or value > 180:
            raise serializers.ValidationError("Longitud debe estar entre -180 y 180")
        return value


class BulkWorkerResultSerializer(serializers.Serializer):
    """
    Serializer para el resultado de la carga masiva
    """
    total_processed = serializers.IntegerField()
    successful = serializers.IntegerField()
    failed = serializers.IntegerField()
    success_details = serializers.ListField(
        child=serializers.DictField()
    )
    error_details = serializers.ListField(
        child=serializers.DictField()
    )
    execution_time = serializers.FloatField()