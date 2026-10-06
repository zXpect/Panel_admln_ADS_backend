from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from ...guards import check_payment_mode
from .base import BaseGateway, CheckoutSession, GatewayEvent


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

    # PAGOS_MODO=wompi: WompiGateway se implementa en la Fase 7 (requiere llaves Sandbox)
    raise ImproperlyConfigured('WompiGateway aún no está implementado')


__all__ = ['BaseGateway', 'CheckoutSession', 'GatewayEvent', 'get_gateway']
