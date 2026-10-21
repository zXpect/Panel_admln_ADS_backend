from django.core.exceptions import ImproperlyConfigured

VALID_MODES = ('mock', 'wompi')


def check_payment_mode(django_env, mode):
    """
    Valida la combinación entorno/pasarela. El mock jamás se activa en
    producción: si DJANGO_ENV=production y PAGOS_MODO=mock, el backend no arranca.

    Raises:
        ImproperlyConfigured
    """
    if mode not in VALID_MODES:
        raise ImproperlyConfigured(
            f"PAGOS_MODO inválido: '{mode}'. Valores permitidos: {', '.join(VALID_MODES)}"
        )
    if django_env == 'production' and mode == 'mock':
        raise ImproperlyConfigured(
            'PAGOS_MODO=mock no está permitido con DJANGO_ENV=production'
        )
