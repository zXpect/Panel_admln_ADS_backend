from rest_framework import serializers

from worker_verification.models import SystemConfig

from ..models import ServiceCategory, Task


class AdminTaskSerializer(serializers.ModelSerializer):
    """Tarea del catálogo para el panel (B10): incluye las inactivas y la referencia sin ajustar."""
    category = serializers.SlugRelatedField(slug_field='slug', queryset=ServiceCategory.objects.all())

    class Meta:
        model = Task
        fields = ('id', 'category', 'slug', 'name', 'unit', 'reference_min_cop', 'reference_max_cop',
                  'source', 'is_active', 'order')
        read_only_fields = ('id',)

    def validate(self, attrs):
        instance = self.instance
        category = attrs.get('category', instance.category if instance else None)
        slug = attrs.get('slug', instance.slug if instance else None)
        if instance and 'category' in attrs and attrs['category'] != instance.category:
            # Las solicitudes guardan el slug de la tarea junto al del oficio
            raise serializers.ValidationError({'category': ['Una tarea no cambia de oficio']})
        duplicates = Task.objects.filter(category=category, slug=slug)
        if instance:
            duplicates = duplicates.exclude(pk=instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError({'slug': ['Ya existe una tarea con ese slug en el oficio']})

        min_cop = attrs.get('reference_min_cop', instance.reference_min_cop if instance else None)
        max_cop = attrs.get('reference_max_cop', instance.reference_max_cop if instance else None)
        if (min_cop is None) != (max_cop is None):
            raise serializers.ValidationError(
                {'reference_min_cop': ['El rango va completo (mínimo y máximo) o vacío']})
        if min_cop is not None and min_cop > max_cop:
            raise serializers.ValidationError({'reference_min_cop': ['El mínimo no puede ser mayor que el máximo']})
        return attrs


class AdminCategorySerializer(serializers.ModelSerializer):
    """Oficio para el panel. El slug no cambia: lo usan la app y las solicitudes guardadas."""
    tasks = AdminTaskSerializer(many=True, read_only=True)

    class Meta:
        model = ServiceCategory
        fields = ('id', 'slug', 'name', 'is_active', 'order', 'tasks')
        read_only_fields = ('id', 'slug', 'tasks')


def _number(value, cast, minimum, maximum):
    try:
        number = cast(value)
    except (TypeError, ValueError):
        raise serializers.ValidationError('Debe ser un número' + (' entero' if cast is int else ''))
    if not minimum <= number <= maximum:
        raise serializers.ValidationError(f'Debe estar entre {minimum} y {maximum}')
    return str(number)


class AdminConfigSerializer(serializers.ModelSerializer):
    """
    Parámetro de SystemConfig. Las claves que usa el cálculo de precios y la
    búsqueda tienen formato y rango; las demás se guardan como texto.
    """
    # clave -> (tipo, mínimo, máximo)
    FORMATS = {
        'quote_regional_factor_pct': (int, -90, 100),
        'quote_min_visit_fee_cop': (int, 1, 50_000_000),
        'quote_max_price_cop': (int, 1, 50_000_000),
        'worker_max_categories': (int, 1, 7),
        'search_weight_distance': (float, 0, 1),
        'search_weight_rating': (float, 0, 1),
        'search_neutral_rating': (float, 0, 5),
    }

    class Meta:
        model = SystemConfig
        fields = ('key', 'value', 'description', 'updated_at')
        read_only_fields = ('key', 'description', 'updated_at')

    def validate_value(self, value):
        value = value.strip()
        key = self.instance.key if self.instance else None
        if key in self.FORMATS:
            value = _number(value, *self.FORMATS[key])
        elif not value:
            raise serializers.ValidationError('El valor no puede estar vacío')
        return value

    def validate(self, attrs):
        key = self.instance.key
        limits = {'quote_min_visit_fee_cop', 'quote_max_price_cop'}
        if key in limits:
            values = {item.key: item.value for item in SystemConfig.objects.filter(key__in=limits)}
            values[key] = attrs['value']
            try:
                min_fee, max_price = int(values['quote_min_visit_fee_cop']), int(values['quote_max_price_cop'])
            except (KeyError, ValueError):
                return attrs
            if min_fee >= max_price:
                raise serializers.ValidationError(
                    {'value': ['La tarifa mínima por visita debe ser menor que el precio máximo']})
        return attrs
