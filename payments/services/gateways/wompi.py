import logging
from urllib.parse import urlencode

import requests

from ..signature import integrity_signature
from .base import BaseGateway, CheckoutSession, GatewayTransaction

logger = logging.getLogger(__name__)


class WompiGateway(BaseGateway):
    """
    Pasarela real (Sandbox de Wompi, D17): Web Checkout por URL con firma de
    integridad y eventos 'transaction.updated' firmados con checksum. Los
    eventos tienen la misma estructura que los del mock, así que la
    verificación y el parseo viven en BaseGateway.

    Referencias:
    - Web Checkout: https://docs.wompi.co/docs/colombia/widget-checkout-web/
    - Eventos: https://docs.wompi.co/docs/colombia/eventos/
    - Transacciones: https://docs.wompi.co/docs/colombia/referencia-api/
    """
    name = 'wompi'
    CHECKOUT_URL = 'https://checkout.wompi.co/p/'
    TIMEOUT_SECONDS = 10

    def __init__(self, public_key, private_key, integrity_secret, events_secret, base_url):
        super().__init__(integrity_secret, events_secret)
        if not public_key or not private_key:
            raise ValueError('Faltan las llaves pública y privada de Wompi')
        self.public_key = public_key
        self.private_key = private_key
        self.base_url = base_url.rstrip('/')

    def create_transaction(self, reference, amount_in_cents, currency, redirect_url=None):
        """
        No llama a Wompi: el Web Checkout recibe todo por la URL y la firma de
        integridad impide alterar el monto o la referencia.
        """
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

        return CheckoutSession(
            reference=reference,
            amount_in_cents=amount_in_cents,
            currency=currency,
            integrity_signature=signature,
            checkout_url=f"{self.CHECKOUT_URL}?{urlencode(params)}",
        )

    def find_transaction(self, reference):
        """
        Busca en Wompi la última transacción de una referencia (con la llave
        privada). Sirve para no dar por abandonado un pago que sí se aprobó
        cuando el evento no llegó.

        Returns:
            GatewayTransaction o None si no hay transacción o Wompi no responde
        """
        try:
            response = requests.get(
                f"{self.base_url}/transactions",
                params={'reference': reference},
                headers={'Authorization': f"Bearer {self.private_key}"},
                timeout=self.TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            transactions = response.json().get('data') or []
        except (requests.RequestException, ValueError, AttributeError) as e:
            logger.warning(f"Could not query Wompi for {reference}: {str(e)}")
            return None

        matches = [t for t in transactions if isinstance(t, dict) and t.get('reference') == reference]
        if not matches:
            return None
        # Si hubo varios intentos con la misma referencia, gana el aprobado
        transaction = next((t for t in matches if t.get('status') == 'APPROVED'), matches[0])
        amount = transaction.get('amount_in_cents')
        if not isinstance(amount, int) or isinstance(amount, bool):
            return None
        return GatewayTransaction(
            transaction_id=str(transaction.get('id', '')),
            status=transaction.get('status', ''),
            amount_in_cents=amount,
        )
