import unicodedata

# Valores del campo viejo `work` que no coinciden con un slug (PLAN_CATALOGO_TAREAS.md §7,
# más los nombres de persona que aparecen en los datos reales, como «Plomero» o «Carpintero»).
# Plomería, Albañilería, Jardinería, Carpintería y Cerrajería coinciden con el slug
# al quitar tildes y mayúsculas. Ferretería no tiene oficio: revisión manual.
LEGACY_WORK_TO_CATEGORY = {
    'electricista': 'electricidad',
    'plomero': 'plomeria',
    'pintor': 'pintura',
    'albanil': 'albanileria',
    'cerrajero': 'cerrajeria',
    'jardinero': 'jardineria',
    'carpintero': 'carpinteria',
}


def normalize(value):
    """'Plomería ' -> 'plomeria' (sin tildes, minúsculas, sin espacios a los lados)."""
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode()
    return text.strip().lower()


def legacy_work_to_category(work, valid_slugs):
    """Slug del oficio que corresponde al texto de `work`, o None si no hay equivalencia."""
    value = normalize(work)
    slug = LEGACY_WORK_TO_CATEGORY.get(value, value)
    return slug if slug in valid_slugs else None


def as_list(value):
    """Firebase devuelve las listas como list o, si tienen huecos, como dict {índice: valor}."""
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, list):
        return [item for item in value if item is not None]
    return []


def resolve_worker_categories(values):
    """
    Oficios que el panel o la carga masiva le asignan a un trabajador (D16), igual
    que en el registro de la app: slugs de oficios activos del catálogo, sin
    repetir y como máximo `worker_max_categories`. Acepta el slug, el nombre o un
    valor viejo de `work` ('Plomero').

    Devuelve (slugs, work), con `work` = nombre del primer oficio, que la app
    sigue escribiendo como respaldo. Lanza ValueError con un mensaje para el administrador.
    """
    from ..models import ServiceCategory
    from .pricing_service import pricing_service

    names = dict(ServiceCategory.objects.filter(is_active=True).values_list('slug', 'name'))
    slugs, unknown = [], []
    for value in values:
        if not str(value or '').strip():
            continue
        slug = legacy_work_to_category(value, names)
        if slug is None:
            unknown.append(str(value).strip())
        elif slug not in slugs:
            slugs.append(slug)

    if unknown:
        raise ValueError(f"Oficio no válido o inactivo: {', '.join(unknown)}")
    if not slugs:
        raise ValueError('Elige al menos un oficio')
    max_categories = pricing_service.config_int(pricing_service.CONFIG_WORKER_MAX_CATEGORIES)
    if len(slugs) > max_categories:
        raise ValueError(f'Máximo {max_categories} oficios por trabajador')
    return slugs, names[slugs[0]]


def worker_categories(worker, valid_slugs):
    """
    Oficios del trabajador: `categories` si ya existe; si no, el oficio que se
    deduce del campo viejo `work` (respaldo hasta migrar con migrate_worker_categories).
    """
    categories = [slug for slug in as_list(worker.get('categories')) if slug in valid_slugs]
    if categories:
        return set(categories)
    legacy = legacy_work_to_category(worker.get('work'), valid_slugs)
    return {legacy} if legacy else set()
