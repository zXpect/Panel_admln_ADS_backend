from rest_framework import serializers


class DocumentSerializer(serializers.Serializer):
    """
    Serializer para documentos
    """
    id = serializers.CharField(required=True)
    workerId = serializers.CharField(required=True)
    documentType = serializers.CharField(required=True)
    category = serializers.CharField(required=True)
    subcategory = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    fileName = serializers.CharField(required=True)
    fileUrl = serializers.CharField(required=True)
    fileType = serializers.CharField(required=True)
    fileSize = serializers.IntegerField(required=True)
    status = serializers.CharField(read_only=True)
    uploadedAt = serializers.IntegerField(read_only=True)
    reviewedAt = serializers.IntegerField(required=False, default=0)
    reviewedBy = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    rejectionReason = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    orden = serializers.IntegerField(required=False, default=0)
    verificationUrl = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    
    def validate_fileType(self, value):
        """Valida que el tipo de archivo sea permitido"""
        allowed_types = ['application/pdf', 'image/jpeg', 'image/jpg', 'image/png']
        if value not in allowed_types:
            raise serializers.ValidationError(f"Tipo de archivo no permitido. Permitidos: {', '.join(allowed_types)}")
        return value
    
    def validate_fileSize(self, value):
        """Valida que el tamaño del archivo no exceda 10MB"""
        max_size = 10 * 1024 * 1024  # 10MB
        if value > max_size:
            raise serializers.ValidationError("El archivo no puede exceder 10MB")
        return value


class DocumentApprovalSerializer(serializers.Serializer):
    """
    Serializer para aprobar documentos
    """
    reviewerId = serializers.CharField(required=True)


class DocumentRejectionSerializer(serializers.Serializer):
    """
    Serializer para rechazar documentos
    """
    reviewerId = serializers.CharField(required=True)
    reason = serializers.CharField(required=True, min_length=10)
    
    def validate_reason(self, value):
        """Valida que la razón tenga contenido significativo"""
        if not value.strip():
            raise serializers.ValidationError("Debe proporcionar una razón válida para el rechazo")
        return value.strip()


class DocumentStatusUpdateSerializer(serializers.Serializer):
    """
    Serializer para actualizar estado de documento
    """
    status = serializers.ChoiceField(
        choices=['pending', 'approved', 'rejected'],
        required=True
    )
    



class DocumentRequirementCheckSerializer(serializers.Serializer):
    """
    Serializer para verificación de documentos requeridos
    """
    hasHojaVida = serializers.BooleanField()
    hasAntecedentes = serializers.BooleanField()
    hasTitulo = serializers.BooleanField()
    cartasCount = serializers.IntegerField()
    hasMinimumCartas = serializers.BooleanField()
    isComplete = serializers.SerializerMethodField()

    def get_isComplete(self, obj):
        """
        Reglas:
        - Hoja de vida y antecedentes son obligatorios
        - Luego: o tiene título o al menos 3 cartas
        """
        has_hoja = obj.get("hasHojaVida", False)
        has_ant = obj.get("hasAntecedentes", False)
        has_titulo = obj.get("hasTitulo", False)
        has_min_cartas = obj.get("hasMinimumCartas", False)

        return has_hoja and has_ant and (has_titulo or has_min_cartas)


class DocumentListSerializer(serializers.Serializer):
    """
    Serializer simplificado para listados
    """
    id = serializers.CharField()
    workerId = serializers.CharField()
    documentType = serializers.CharField()
    category = serializers.CharField()
    fileName = serializers.CharField()
    status = serializers.CharField()
    uploadedAt = serializers.IntegerField()
    reviewedAt = serializers.IntegerField(required=False)