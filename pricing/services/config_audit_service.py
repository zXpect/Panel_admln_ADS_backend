from ..models import ConfigAuditLog, ServiceCategory, Task


class ConfigAuditService:
    """
    Registra en ConfigAuditLog los cambios de oficios, tareas y parámetros (I10).
    Se llama dentro de la misma transacción que guarda el cambio.
    """

    @staticmethod
    def snapshot(instance):
        """Valor auditable de un objeto (sin id; el oficio de la tarea, por slug)."""
        if instance is None:
            return None
        if isinstance(instance, ServiceCategory):
            return {'slug': instance.slug, 'name': instance.name,
                    'is_active': instance.is_active, 'order': instance.order}
        if isinstance(instance, Task):
            return {'category': instance.category.slug, 'slug': instance.slug, 'name': instance.name,
                    'unit': instance.unit, 'reference_min_cop': instance.reference_min_cop,
                    'reference_max_cop': instance.reference_max_cop, 'source': instance.source,
                    'is_active': instance.is_active, 'order': instance.order}
        # SystemConfig
        return {'value': instance.value, 'description': instance.description}

    @staticmethod
    def entity_key(instance):
        if isinstance(instance, Task):
            return f"{instance.category.slug}/{instance.slug}"
        if isinstance(instance, ServiceCategory):
            return instance.slug
        return instance.key

    def log_change(self, admin, old_instance, new_instance):
        old_value = self.snapshot(old_instance)
        new_value = self.snapshot(new_instance)
        if old_value == new_value:
            return None
        return ConfigAuditLog.objects.create(
            admin=admin,
            entity=type(new_instance).__name__,
            entity_key=self.entity_key(new_instance),
            old_value=old_value,
            new_value=new_value,
        )


config_audit_service = ConfigAuditService()
