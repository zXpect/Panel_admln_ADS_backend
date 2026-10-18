from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from ...guards import check_payment_mode
from .base import BaseGateway, CheckoutSession, GatewayEvent, GatewayTransaction


def get_gateway():
    """
    Devuelve la pasarela activa según PAGOS_MODO. Vuelve a aplicar el guard
    de producción para no procesar pagos simulados aunque se salte el arranque.
    """
    config = settings.PAYMENTS
    mode = config['MODE']
    check_payment_mode(settings.DJANGO_ENV, mode)

    if mode == 'mock':
        from .mock import MockGateway
        return MockGateway(
            integrity_secret=config['MOCK']['INTEGRITY_SECRET'],
            events_secret=config['MOCK']['EVENTS_SECRET'],
            checkout_base_url=config['MOCK']['CHECKOUT_BASE_URL'],
        )

    from .wompi import WompiGateway
    wompi = config['WOMPI']
    try:
        return WompiGateway(
            public_key=wompi['PUBLIC_KEY'],
            private_key=wompi['PRIVATE_KEY'],
            integrity_secret=wompi['INTEGRITY_SECRET'],
            events_secret=wompi['EVENTS_SECRET'],
            base_url=wompi['BASE_URL'],
        )
    except ValueError as e:
        raise ImproperlyConfigured(f"PAGOS_MODO=wompi: {e}") from e


__all__ = ['BaseGateway', 'CheckoutSession', 'GatewayEvent', 'GatewayTransaction', 'get_gateway']
