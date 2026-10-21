from rest_framework import serializers

from .models import PQR


class PqrCreateSerializer(serializers.Serializer):
    service_request_id = serializers.CharField(max_length=255)
    type = serializers.ChoiceField(choices=[value for value, _ in PQR.TYPES])
    description = serializers.CharField(max_length=2000, trim_whitespace=True)

    def validate_service_request_id(self, value):
        if any(char in value for char in '/.#$[]'):
            raise serializers.ValidationError('ID de solicitud inválido')
        return value


class PqrAnswerSerializer(serializers.Serializer):
    """El panel solo pasa la PQR a trámite o la cierra; 'abierta' es el estado inicial."""
    status = serializers.ChoiceField(choices=[PQR.STATUS_IN_PROGRESS, PQR.STATUS_CLOSED])
    response = serializers.CharField(max_length=4000, required=False, allow_blank=True, default='')


class PqrSerializer(serializers.ModelSerializer):
    class Meta:
        model = PQR
        fields = ('id', 'service_request_id', 'author_uid', 'author_role', 'type', 'description', 'status',
                  'response', 'created_at', 'due_at', 'closed_at')


class PqrAdminSerializer(PqrSerializer):
    responded_by = serializers.SlugRelatedField(slug_field='username', read_only=True)
    is_overdue = serializers.SerializerMethodField()

    class Meta(PqrSerializer.Meta):
        fields = PqrSerializer.Meta.fields + ('responded_by', 'is_overdue')

    def get_is_overdue(self, obj):
        from django.utils import timezone
        return obj.status != PQR.STATUS_CLOSED and obj.due_at < timezone.now()
