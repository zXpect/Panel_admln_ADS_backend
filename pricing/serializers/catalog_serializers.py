from decimal import Decimal

from rest_framework import serializers

from ..models import ServiceCategory, Task


class TaskItemSerializer(serializers.Serializer):
    """Un ítem de la solicitud: una tarea del catálogo o «Otro» con descripción libre."""
    MAX_QUANTITY = Decimal('1000')

    task = serializers.SlugField(required=False)
    custom_description = serializers.CharField(max_length=200, required=False, trim_whitespace=True)
    quantity = serializers.DecimalField(
        max_digits=7, decimal_places=2, min_value=Decimal('0.01'), max_value=MAX_QUANTITY)

    def validate(self, attrs):
        has_task = bool(attrs.get('task'))
        has_description = bool(attrs.get('custom_description'))
        if has_task == has_description:
            raise serializers.ValidationError('Cada ítem lleva una tarea del catálogo o una descripción («Otro»), no ambas')
        return attrs


class EstimateSerializer(serializers.Serializer):
    """
    Cuerpo de POST /api/requests/estimate/ (y base de POST /api/requests/).
    Al validar resuelve el oficio y las tareas contra el catálogo activo:
    validated_data incluye 'category' (ServiceCategory) e 'items' ([{'task': Task | None, ...}]).
    """
    MAX_ITEMS = 10

    service_category = serializers.SlugField()
    task_items = serializers.ListField(child=TaskItemSerializer(), min_length=1, max_length=MAX_ITEMS)

    def validate(self, attrs):
        category = ServiceCategory.objects.filter(slug=attrs['service_category'], is_active=True).first()
        if category is None:
            raise serializers.ValidationError({'service_category': ['Oficio inexistente o inactivo']})

        slugs = {item['task'] for item in attrs['task_items'] if item.get('task')}
        tasks = {task.slug: task for task in Task.objects.filter(category=category, is_active=True, slug__in=slugs)}

        errors = {}
        items = []
        for index, item in enumerate(attrs['task_items']):
            quantity = item['quantity']
            slug = item.get('task')
            if slug is None:
                if quantity != quantity.to_integral_value():
                    errors[index] = {'quantity': ['La cantidad de «Otro» debe ser un número entero']}
                    continue
                items.append({'task': None, 'custom_description': item['custom_description'], 'quantity': quantity})
                continue

            task = tasks.get(slug)
            if task is None:
                errors[index] = {'task': ['Tarea inexistente, inactiva o de otro oficio']}
                continue
            # Solo las tareas por m² admiten decimales (Anexo 4)
            if task.unit != Task.UNIT_M2 and quantity != quantity.to_integral_value():
                errors[index] = {'quantity': ['Solo las tareas por m² admiten cantidades decimales']}
                continue
            items.append({'task': task, 'quantity': quantity})

        if errors:
            raise serializers.ValidationError({'task_items': errors})

        return {**attrs, 'category': category, 'items': items}
