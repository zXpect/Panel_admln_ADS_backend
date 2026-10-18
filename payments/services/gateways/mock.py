import random
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

from django.urls import reverse

from ..signature import integrity_signature
from .base import BaseGateway, CheckoutSession

EVENT_SIGNATURE_PROPERTIES = ['transaction.id', 'transaction.status', 'transaction.amount_in_cents']


class MockGateway(BaseGateway):
    """
    Pasarela simulada que replica la estructura de Wompi:
    - checkout por URL con los mismos parámetros que el Web Checkout
      (public-key, currency, amount-in-cents, reference, signature:integrity, redirect-url)
    - eventos 'transaction.updated' firmados con checksum SHA256

    Solo para desarrollo: el guard de payments/guards.py impide usarla en producción.
    """
    name = 'mock'
    public_key = 'pub_mock_ads'

    def __init__(self, integrity_secret, events_secret, checkout_base_url):
        super().__init__(integrity_secret, events_secret)
        self.checkout_base_url = checkout_base_url.rstrip('/')

    def create_transaction(self, reference, amount_in_cents, currency, redirect_url=None):
        signature = integrity_signature(reference, amount_in_cents, currency, self.integrity_secret)

        params = {
            'public-key': self.public_key,
            'currency': currency,
            'amount-in-cents': amount_in_cents,
            'reference': reference,
            'signature:integrity': signature,
        }
        if redirect_url:
            params['redirect-url'] = redirect_url

        path = reverse('payments:mock-checkout', kwargs={'reference': reference})
        checkout_url = f"{self.checkout_base_url}{path}?{urlencode(params)}"

        return CheckoutSession(
            reference=reference,
            amount_in_cents=amount_in_cents,
            currency=currency,
            integrity_signature=signature,
            checkout_url=checkout_url,
        )

    def verify_integrity(self, reference, amount_in_cents, currency, signature):
        """Lo que haría el checkout de Wompi: rechazar un enlace manipulado."""
        try:
            expected = integrity_signature(reference, amount_in_cents, currency, self.integrity_secret)
        except ValueError:
            return False
        return expected == signature

    @staticmethod
    def new_transaction_id():
        # Mismo formato que los IDs de Wompi: <comercio>-<epoch>-<aleatorio>
        return f"mock-{int(time.time())}-{random.randint(10000, 99999)}"

    def build_event(self, reference, transaction_id, status, amount_in_cents, currency, redirect_url=None):
        """
        Construye un evento 'transaction.updated' firmado, igual al que Wompi
        envía a la URL de eventos.
        """
        now = datetime.now(timezone.utc)
        event = {
            'event': 'transaction.updated',
            'data': {
                'transaction': {
                    'id': transaction_id,
                    'amount_in_cents': amount_in_cents,
                    'reference': reference,
                    'currency': currency,
                    'payment_method_type': 'CARD',
                    'redirect_url': redirect_url,
                    'status': status,
                    'status_message': None,
                    'created_at': now.isoformat(),
                    'finalized_at': now.isoformat(),
                }
            },
            'environment': 'test',
            'signature': {
                'properties': list(EVENT_SIGNATURE_PROPERTIES),
                'checksum': '',
            },
            'timestamp': int(now.timestamp()),
            'sent_at': now.isoformat(),
        }
        event['signature']['checksum'] = self.compute_event_checksum(event)
        return event
