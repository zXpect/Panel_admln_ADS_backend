import logging
from decimal import ROUND_HALF_UP, Decimal

from worker_verification.models import SystemConfig

from ..models import ServiceCategory, Task

logger = logging.getLogger(__name__)


def round_to_hundred(value):
    """
    Redondea a la centena más cercana con las mitades hacia arriba, como el
    Anexo 4 (7.650 -> 7.700). round() de Python redondea las mitades al par
    (7.650 -> 7.600), por eso se usa Decimal.
    """
    return int(Decimal(value).quantize(Decimal('1E2'), rounding=ROUND_HALF_UP))


def json_number(value):
    """Decimal -> int si es entero, float si no (Firebase y JSON no tienen Decimal)."""
    return int(value) if value == value.to_integral_value() else float(value)


class PricingService:
    """
    Catálogo de tareas y cálculo del precio de referencia (Anexo 4, D1–D6).
    El resultado de `estimate` es el `quote_reference` que se congela en la
    solicitud al crearla.
    """

    # Claves en SystemConfig (sembradas por la migración 0002 de pricing)
    CONFIG_REGIONAL_FACTOR = 'quote_regional_factor_pct'
    CONFIG_MIN_VISIT_FEE = 'quote_min_visit_fee_cop'
    CONFIG_MAX_PRICE = 'quote_max_price_cop'
    CONFIG_WORKER_MAX_CATEGORIES = 'worker_max_categories'

    DEFAULTS = {
        CONFIG_REGIONAL_FACTOR: -15,
        CONFIG_MIN_VISIT_FEE: 25500,
        CONFIG_MAX_PRICE: 5000000,
        CONFIG_WORKER_MAX_CATEGORIES: 3,
    }

    # ---------- parámetros ----------

    def config_int(self, key):
        config = SystemConfig.objects.filter(key=key).first()
        try:
            return int(config.value) if config else self.DEFAULTS[key]
        except (TypeError, ValueError):
            logger.error(f"Invalid SystemConfig value for {key}")
            return self.DEFAULTS[key]

    def regional_factor_pct(self):
        return self.config_int(self.CONFIG_REGIONAL_FACTOR)

    def min_visit_fee_cop(self):
        return self.config_int(self.CONFIG_MIN_VISIT_FEE)

    def max_price_cop(self):
        return self.config_int(self.CONFIG_MAX_PRICE)

    # ---------- rango de Ubaté ----------

    @staticmethod
    def regional_price(reference_cop, factor_pct, quantity=1):
        """
        Precio unitario de Ubaté (referencia × (1 + factor), a la centena) por
        la cantidad, otra vez a la centena. Se parte del unitario redondeado
        porque es el que el cliente ve en el catálogo (Σ min × cantidad, Anexo 4).
        """
        multiplier = (Decimal(100) + Decimal(factor_pct)) / Decimal(100)
        unit_price = round_to_hundred(Decimal(reference_cop) * multiplier)
        return round_to_hundred(unit_price * Decimal(quantity))

    def task_range(self, task, factor_pct, quantity=1):
        """(min_cop, max_cop) de la tarea para la cantidad dada; (None, None) si no tiene rango."""
        if not task.has_range:
            return None, None
        return (
            self.regional_price(task.reference_min_cop, factor_pct, quantity),
            self.regional_price(task.reference_max_cop, factor_pct, quantity),
        )

    # ---------- catálogo ----------

    def get_catalog(self):
        """Oficios activos con sus tareas activas y el rango ajustado para Ubaté (GET /api/catalog/)."""
        factor_pct = self.regional_factor_pct()
        categories = ServiceCategory.objects.filter(is_active=True).order_by('order', 'name')
        tasks_by_category = {}
        for task in Task.objects.filter(is_active=True, category__in=categories).order_by('order', 'name'):
            tasks_by_category.setdefault(task.category_id, []).append(task)

        result = []
        for category in categories:
            tasks = []
            for task in tasks_by_category.get(category.id, []):
                min_cop, max_cop = self.task_range(task, factor_pct)
                tasks.append({
                    'slug': task.slug, 'name': task.name, 'unit': task.unit,
                    'min_cop': min_cop, 'max_cop': max_cop,
                })
            result.append({'slug': category.slug, 'name': category.name, 'tasks': tasks})

        return {
            'regional_factor_pct': factor_pct,
            'min_visit_fee_cop': self.min_visit_fee_cop(),
            'categories': result,
        }

    # ---------- estimado ----------

    def estimate(self, items):
        """
        Precio de referencia de los ítems ya validados (ver EstimateSerializer):
        cada ítem es {'task': Task, 'quantity': Decimal} o
        {'custom_description': str, 'quantity': Decimal}.

        min_cop/max_cop suman solo los ítems con rango y tienen la tarifa
        mínima por visita como piso (D4). Si ningún ítem tiene rango son None:
        el trabajador cotiza todo con motivo.
        """
        factor_pct = self.regional_factor_pct()
        min_visit_fee = self.min_visit_fee_cop()

        detail = []
        total_min = total_max = 0
        priced_items = 0
        for item in items:
            quantity = item['quantity']
            task = item.get('task')
            if task is None:
                detail.append({
                    'custom_description': item['custom_description'],
                    'quantity': json_number(quantity),
                    'unit': None, 'min_cop': None, 'max_cop': None,
                })
                continue

            min_cop, max_cop = self.task_range(task, factor_pct, quantity)
            if min_cop is not None:
                total_min += min_cop
                total_max += max_cop
                priced_items += 1
            detail.append({
                'task': task.slug,
                'quantity': json_number(quantity),
                'unit': task.unit, 'min_cop': min_cop, 'max_cop': max_cop,
            })

        return {
            'min_cop': max(total_min, min_visit_fee) if priced_items else None,
            'max_cop': max(total_max, min_visit_fee) if priced_items else None,
            'regional_factor_pct': factor_pct,
            'min_visit_fee_cop': min_visit_fee,
            'has_unpriced_items': priced_items < len(items),
            'items': detail,
        }


pricing_service = PricingService()
