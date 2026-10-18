from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..signature import verify_event_checksum, event_checksum


@dataclass(frozen=True)
class CheckoutSession:
    """Resultado de crear una transacción: lo que la app necesita para pagar."""
    reference: str
    amount_in_cents: int
    currency: str
    integrity_signature: str
    checkout_url: str


@dataclass(frozen=True)
class GatewayEvent:
    """Evento de la pasarela ya normalizado."""
    event_type: str
    reference: str
    transaction_id: str
    status: str
    amount_in_cents: int
    checksum: str
    payload: dict


class BaseGateway(ABC):
    """
    Interfaz común de pasarelas. Los eventos del mock y de Wompi tienen la
    misma estructura, así que verify_event/parse_event viven aquí; cada
    pasarela solo define cómo crear la transacción y sus secretos.
    """
    name = None

    def __init__(self, integrity_secret, events_secret):
        if not integrity_secret or not events_secret:
            raise ValueError(f'Faltan los secretos de la pasarela {self.name}')
        self.integrity_secret = integrity_secret
        self.events_secret = events_secret

    @abstractmethod
    def create_transaction(self, reference, amount_in_cents, currency, redirect_url=None):
        """
        Returns:
            CheckoutSession
        """

    def verify_event(self, payload, header_checksum=None):
        return verify_event_checksum(payload, self.events_secret, header_checksum)

    def parse_event(self, payload):
        """
        Extrae los datos de un evento 'transaction.updated'.

        Raises:
            ValueError: si el payload no tiene la estructura esperada
        """
        try:
            transaction = payload['data']['transaction']
            event = GatewayEvent(
                event_type=payload['event'],
                reference=transaction['reference'],
                transaction_id=str(transaction['id']),
                status=transaction['status'],
                amount_in_cents=transaction['amount_in_cents'],
                checksum=str(payload['signature']['checksum']).upper(),
                payload=payload,
            )
        except (KeyError, TypeError):
            raise ValueError('Evento con estructura inválida')

        if not isinstance(event.amount_in_cents, int) or isinstance(event.amount_in_cents, bool):
            raise ValueError('amount_in_cents del evento debe ser un entero')
        return event

    def compute_event_checksum(self, payload):
        """Usado por el mock para firmar los eventos que genera."""
        return event_checksum(payload, self.events_secret)
