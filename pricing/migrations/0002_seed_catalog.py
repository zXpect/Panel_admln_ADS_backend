"""
Semilla inicial del catálogo (PLAN_CATALOGO_TAREAS.md §2, decisiones D1–D3) y
claves de SystemConfig de la cotización y la búsqueda.

Los rangos son la referencia de ciudades grandes de la Tabla 5 del Anexo 4;
el rango de Ubaté se calcula con `quote_regional_factor_pct`. Los datos van
escritos aquí (y no importados de la app) para que la migración no cambie si
el código cambia después.
"""
from django.db import migrations

COLOMBIA_MOVE = 'Colombia Move (2026)'
ONE_ESTIMATE_A = 'OneEstimate (2026a)'
ONE_ESTIMATE_B = 'OneEstimate (2026b)'

# (slug, nombre, [(slug, nombre, unidad, ref_min, ref_max, fuente)])
CATALOG = [
    ('electricidad', 'Electricidad', [
        ('breaker-falla-simple', 'Breaker o falla simple', 'visita', 40000, 80000, COLOMBIA_MOVE),
        ('instalar-lampara-ventilador', 'Instalar lámpara o ventilador', 'unidad', 60000, 120000, COLOMBIA_MOVE),
        ('instalar-tomacorriente', 'Instalar tomacorriente', 'unidad', 80000, 150000, COLOMBIA_MOVE),
        ('diagnosticar-reparar-circuito', 'Diagnosticar y reparar circuito', 'visita', 100000, 250000, COLOMBIA_MOVE),
        ('instalar-punto-electrico', 'Instalar punto eléctrico nuevo', 'unidad', None, None, ''),
    ]),
    ('plomeria', 'Plomería', [
        ('destapar-desague-sanitario', 'Destapar desagüe o sanitario', 'visita', 30000, 60000, COLOMBIA_MOVE),
        ('reparar-grifo-valvula', 'Reparar grifo o válvula', 'unidad', 50000, 120000, COLOMBIA_MOVE),
        ('instalar-calentador', 'Instalar calentador de agua', 'unidad', 200000, 350000, COLOMBIA_MOVE),
        ('reparar-fuga-tuberia', 'Reparar fuga en tubería', 'visita', None, None, ''),
        ('cambiar-griferia-sanitario', 'Cambiar grifería o sanitario', 'unidad', None, None, ''),
        ('revisar-presion-agua', 'Revisar presión de agua', 'visita', None, None, ''),
        ('instalar-reparar-tanque', 'Instalar o reparar tanque', 'unidad', None, None, ''),
    ]),
    ('pintura', 'Pintura', [
        ('pintura-estuco-2-manos', 'Pintura sobre estuco, 2 manos', 'm2', 7000, 9000, ONE_ESTIMATE_A),
        ('estuco-pintura-3-manos', 'Estuco y pintura, 3 manos', 'm2', 17500, 22000, ONE_ESTIMATE_A),
        ('pintar-puerta-esmalte', 'Pintar puerta con esmalte', 'unidad', 23000, 35000, ONE_ESTIMATE_A),
        ('pintar-ventana', 'Pintar ventana', 'unidad', None, None, ''),
    ]),
    ('albanileria', 'Albañilería', [
        ('instalar-ceramica-piso', 'Instalar cerámica de piso', 'm2', 24000, 29500, ONE_ESTIMATE_B),
        ('enchape-muros-bano', 'Enchape de muros de baño', 'm2', 28500, 35000, ONE_ESTIMATE_B),
        ('panete-liso-muros', 'Pañete liso en muros', 'm2', 18500, 22000, ONE_ESTIMATE_B),
        ('muro-bloque-concreto', 'Muro en bloque de concreto', 'm2', 28000, 33000, ONE_ESTIMATE_B),
        ('alistado-piso', 'Alistado de piso', 'm2', 14000, 17500, ONE_ESTIMATE_B),
        ('maestro-obra-jornada', 'Maestro de obra (trabajos varios)', 'jornada', 100000, 180000, COLOMBIA_MOVE),
        ('reparar-grietas-humedades', 'Reparar grietas o humedades', 'm2', None, None, ''),
    ]),
    ('cerrajeria', 'Cerrajería', [
        ('abrir-puerta', 'Abrir puerta', 'visita', None, None, ''),
        ('cambiar-guardas-chapa', 'Cambiar guardas o chapa', 'unidad', None, None, ''),
        ('copia-llaves', 'Hacer copia de llaves', 'unidad', None, None, ''),
        ('instalar-cerradura', 'Instalar cerradura nueva', 'unidad', None, None, ''),
    ]),
    ('jardineria', 'Jardinería', [
        ('podar-cesped', 'Podar césped', 'm2', None, None, ''),
        ('podar-cortar-arboles', 'Podar o cortar árboles', 'unidad', None, None, ''),
        ('limpiar-jardin-maleza', 'Limpiar jardín o maleza', 'm2', None, None, ''),
        ('mantenimiento-mensual', 'Mantenimiento mensual', 'visita', None, None, ''),
    ]),
    ('carpinteria', 'Carpintería', [
        ('reparar-puerta-ventana-madera', 'Reparar puerta o ventana de madera', 'unidad', None, None, ''),
        ('instalar-mueble', 'Instalar mueble', 'unidad', None, None, ''),
        ('ajustar-bisagras-cajones', 'Ajustar bisagras o cajones', 'visita', None, None, ''),
    ]),
]

CONFIG = [
    ('quote_regional_factor_pct', '-15',
     'Factor regional (%) sobre la referencia de ciudades grandes para el rango de Ubaté (Anexo 4)'),
    ('quote_min_visit_fee_cop', '25500',
     'Tarifa mínima por visita (COP): piso de cualquier estimado y cotización (D4)'),
    ('quote_max_price_cop', '5000000',
     'Tope técnico de una cotización (COP); no se muestra al cliente (D6)'),
    ('worker_max_categories', '3', 'Oficios máximos por trabajador (D16)'),
    ('search_weight_distance', '0.7', 'Peso de la cercanía en el orden de búsqueda (D13)'),
    ('search_weight_rating', '0.3', 'Peso de la calificación en el orden de búsqueda (D13)'),
    ('search_neutral_rating', '3.0', 'Calificación neutra del trabajador sin calificaciones (D13)'),
]


def seed(apps, schema_editor):
    ServiceCategory = apps.get_model('pricing', 'ServiceCategory')
    Task = apps.get_model('pricing', 'Task')
    SystemConfig = apps.get_model('worker_verification', 'SystemConfig')

    for category_order, (slug, name, tasks) in enumerate(CATALOG, start=1):
        category, _ = ServiceCategory.objects.get_or_create(
            slug=slug, defaults={'name': name, 'order': category_order})
        for task_order, (task_slug, task_name, unit, ref_min, ref_max, source) in enumerate(tasks, start=1):
            Task.objects.get_or_create(category=category, slug=task_slug, defaults={
                'name': task_name, 'unit': unit,
                'reference_min_cop': ref_min, 'reference_max_cop': ref_max,
                'source': source, 'order': task_order,
            })

    # Si un parámetro ya existe (configurado a mano), se respeta su valor
    for key, value, description in CONFIG:
        SystemConfig.objects.get_or_create(key=key, defaults={'value': value, 'description': description})


def unseed(apps, schema_editor):
    ServiceCategory = apps.get_model('pricing', 'ServiceCategory')
    Task = apps.get_model('pricing', 'Task')
    slugs = [slug for slug, _, _ in CATALOG]
    Task.objects.filter(category__slug__in=slugs).delete()
    ServiceCategory.objects.filter(slug__in=slugs).delete()
    # Las claves de SystemConfig se dejan: pueden tener valores ajustados por el administrador


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0001_initial'),
        ('worker_verification', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
