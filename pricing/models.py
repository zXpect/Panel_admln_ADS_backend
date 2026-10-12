from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q


class ServiceCategory(models.Model):
    """
    Oficio del catálogo (Electricidad, Plomería...). El slug es el valor que
    se guarda en Firebase (`service_category`, `categories` del trabajador).
    """
    slug = models.SlugField(unique=True, verbose_name='Slug')
    name = models.CharField(max_length=60, verbose_name='Nombre')
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    order = models.PositiveSmallIntegerField(default=0, verbose_name='Orden')

    class Meta:
        verbose_name = 'Oficio'
        verbose_name_plural = 'Oficios'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class Task(models.Model):
    """
    Tarea predeterminada de un oficio. Guarda la referencia de ciudades
    grandes; el rango de Ubaté se calcula con el factor regional vigente.
    Las tareas no se borran, se desactivan: las solicitudes las referencian por slug.
    """
    UNIT_VISIT = 'visita'
    UNIT_UNIT = 'unidad'
    UNIT_M2 = 'm2'
    UNIT_DAY = 'jornada'
    UNIT_CHOICES = [
        (UNIT_VISIT, 'Visita'),
        (UNIT_UNIT, 'Unidad'),
        (UNIT_M2, 'm²'),
        (UNIT_DAY, 'Jornada'),
    ]

    category = models.ForeignKey(
        ServiceCategory, related_name='tasks', on_delete=models.PROTECT, verbose_name='Oficio')
    slug = models.SlugField(verbose_name='Slug')
    name = models.CharField(max_length=120, verbose_name='Nombre')
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, verbose_name='Unidad de cobro')
    reference_min_cop = models.PositiveIntegerField(
        null=True, blank=True, verbose_name='Referencia mínima (COP, ciudades grandes)')
    reference_max_cop = models.PositiveIntegerField(
        null=True, blank=True, verbose_name='Referencia máxima (COP, ciudades grandes)')
    source = models.CharField(max_length=120, blank=True, verbose_name='Fuente')
    is_active = models.BooleanField(default=True, verbose_name='Activa')
    order = models.PositiveSmallIntegerField(default=0, verbose_name='Orden')

    class Meta:
        verbose_name = 'Tarea'
        verbose_name_plural = 'Tareas'
        ordering = ['category__order', 'order', 'name']
        constraints = [
            models.UniqueConstraint(fields=['category', 'slug'], name='pricing_task_unique_slug_per_category'),
            # Sin rango (ambos nulos) o rango completo con min <= max
            models.CheckConstraint(
                check=(
                    Q(reference_min_cop__isnull=True, reference_max_cop__isnull=True)
                    | Q(reference_min_cop__isnull=False, reference_max_cop__isnull=False,
                        reference_min_cop__lte=models.F('reference_max_cop'))
                ),
                name='pricing_task_valid_reference_range',
            ),
        ]

    def __str__(self):
        return f"{self.category.name} – {self.name}"

    @property
    def has_range(self):
        return self.reference_min_cop is not None


class ConfigAuditLog(models.Model):
    """
    Registro de cada cambio de oficio, tarea o parámetro de SystemConfig hecho
    por un administrador (I10). En el Sprint 4 los cambios se hacen desde el
    admin de Django; en el Sprint 5, desde el panel (B10).
    """
    ENTITY_CHOICES = [
        ('SystemConfig', 'Parámetro'),
        ('ServiceCategory', 'Oficio'),
        ('Task', 'Tarea'),
    ]

    admin = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name='Administrador')
    entity = models.CharField(max_length=30, choices=ENTITY_CHOICES, verbose_name='Entidad')
    entity_key = models.CharField(max_length=120, verbose_name='Clave')
    old_value = models.JSONField(null=True, blank=True, verbose_name='Valor anterior')
    new_value = models.JSONField(verbose_name='Valor nuevo')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha')

    class Meta:
        verbose_name = 'Auditoría de configuración'
        verbose_name_plural = 'Auditoría de configuración'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.entity} {self.entity_key} ({self.admin})"
