import unicodedata

# Valores del campo viejo `work` que no coinciden con un slug (PLAN_CATALOGO_TAREAS.md §7).
# Plomería, Albañilería, Jardinería, Carpintería y Cerrajería coinciden con el slug
# al quitar tildes y mayúsculas. Ferretería no tiene oficio: revisión manual.
LEGACY_WORK_TO_CATEGORY = {
    'electricista': 'electricidad',
    'pintor': 'pintura',
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
