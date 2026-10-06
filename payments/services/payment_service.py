import logging
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from worker_verification.services.firebase_service import firebase_service

from ..models import Payment, PaymentEvent
from .gateways import get_gateway

logger = logging.getLogger(__name__)


class FirebaseSyncError(Exception):
    """El pago quedó actualizado en SQLite pero no se pudo reflejar en Firebase."""


@dataclass(frozen=True)
class EventResult:
    """Resultado de procesar un evento de la pasarela (lo traduce la vista a HTTP)."""
    outcome: str
    payment: Payment = None

    # Resultados posibles
    APPLIED = 'applied'                  # cambió el estado del pago
    DUPLICATE = 'duplicate'              # el pago ya estaba en ese estado (reintento de la pasarela)
    IGNORED = 'ignored'                  # transición inválida, monto distinto o estado no final
    UNKNOWN_REFERENCE = 'unknown_reference'
    INVALID_CHECKSUM = 'invalid_checksum'
    MALFORMED = 'malformed'


class PaymentService:
    """
    Lógica de pagos independiente de la pasarela. El libro de transacciones
    vive en SQLite (Payment/PaymentEvent); el estado que lee la app se
    refleja en Firebase dentro de la solicitud de servicio.
    """

    REQUESTS_PATH = 'requests'

    # Estados que Firebase guarda en minúscula, igual que 'status' de la solicitud
    FIREBASE_PAYMENT_STATUS = {
        Payment.STATUS_PENDING: 'pending',
        Payment.STATUS_APPROVED: 'approved',
        Payment.STATUS_DECLINED: 'declined',
        Payment.STATUS_ERROR: 'error',
        Payment.STATUS_VOIDED: 'voided',
    }

    # Estados de una transacción de Wompi que cierran el pago
    FINAL_GATEWAY_STATUSES = {
        Payment.STATUS_APPROVED,
        Payment.STATUS_DECLINED,
        Payment.STATUS_ERROR,
        Payment.STATUS_VOIDED,
    }

    def __init__(self):
        self.firebase = firebase_service

    @staticmethod
    def generate_reference():
        return f"ADS-{uuid.uuid4().hex[:20].upper()}"

    def create_payment(self, service_request_id, client_uid, worker_uid, amount_in_cents, redirect_url=None):
        """
        Crea un Payment PENDING y la sesión de checkout en la pasarela activa.
        El monto debe venir calculado por el servidor (cotización aceptada),
        nunca desde la app.

        Returns:
            tuple: (Payment, CheckoutSession)
        """
        gateway = get_gateway()
        currency = settings.PAYMENTS['CURRENCY']
        reference = self.generate_reference()

        session = gateway.create_transaction(reference, amount_in_cents, currency, redirect_url)

        payment = Payment.objects.create(
            reference=reference,
            service_request_id=service_request_id,
            client_uid=client_uid,
            worker_uid=worker_uid,
            amount_in_cents=amount_in_cents,
            currency=currency,
            gateway=gateway.name,
        )
        logger.info(f"Payment created: {reference} for request {service_request_id}")

        self.sync_to_firebase(payment)
        return payment, session

    def process_event(self, payload, header_checksum=None):
        """
        Procesa un evento de la pasarela. Es idempotente: el mismo evento
        recibido varias veces no duplica efectos. Todos los eventos quedan
        registrados en PaymentEvent, incluso los inválidos.

        Raises:
            FirebaseSyncError: el estado se guardó pero Firebase falló. La vista
                responde 500 para que la pasarela reintente; el reintento entra
                como DUPLICATE y vuelve a sincronizar.
        """
        gateway = get_gateway()
        event_type = payload.get('event', '') if isinstance(payload, dict) else ''
        raw_checksum = self._raw_checksum(payload)

        if not gateway.verify_event(payload, header_checksum):
            logger.warning(f"Payment event with invalid checksum: {event_type}")
            self._log_event(None, event_type, payload, raw_checksum, checksum_valid=False)
            return EventResult(EventResult.INVALID_CHECKSUM)

        try:
            event = gateway.parse_event(payload)
        except ValueError as e:
            logger.warning(f"Malformed payment event: {str(e)}")
            self._log_event(None, event_type, payload, raw_checksum, checksum_valid=True)
            return EventResult(EventResult.MALFORMED)

        with transaction.atomic():
            payment = Payment.objects.select_for_update().filter(reference=event.reference).first()
            self._log_event(payment, event.event_type, payload, event.checksum, checksum_valid=True)

            if payment is None:
                logger.warning(f"Payment event for unknown reference: {event.reference}")
                return EventResult(EventResult.UNKNOWN_REFERENCE)

            result = self._apply_event(payment, event)

        if result.outcome in (EventResult.APPLIED, EventResult.DUPLICATE):
            self.sync_to_firebase(payment)
        return result

    def _apply_event(self, payment, event):
        if event.amount_in_cents != payment.amount_in_cents:
            logger.error(
                f"Amount mismatch for {payment.reference}: "
                f"expected {payment.amount_in_cents}, got {event.amount_in_cents}"
            )
            return EventResult(EventResult.IGNORED, payment)

        if event.status == payment.status:
            return EventResult(EventResult.DUPLICATE, payment)

        if event.status not in self.FINAL_GATEWAY_STATUSES:
            return EventResult(EventResult.IGNORED, payment)

        if not payment.can_transition_to(event.status):
            logger.warning(f"Invalid transition for {payment.reference}: {payment.status} -> {event.status}")
            return EventResult(EventResult.IGNORED, payment)

        logger.info(f"Payment {payment.reference}: {payment.status} -> {event.status}")
        payment.status = event.status
        payment.gateway_transaction_id = event.transaction_id
        payment.save(update_fields=['status', 'gateway_transaction_id', 'updated_at'])
        return EventResult(EventResult.APPLIED, payment)

    def sync_to_firebase(self, payment):
        """
        Refleja el estado del pago en requests/<id> (payment_status, payment_reference).

        Si la solicitud ya apunta a otro pago (un reintento más reciente), un
        evento tardío del pago anterior no la pisa, salvo que sea APPROVED:
        en ese caso el dinero sí se cobró y la solicitud debe quedar pagada.
        """
        path = f"{self.REQUESTS_PATH}/{payment.service_request_id}"
        try:
            current_reference = self.firebase.get_data(f"{path}/payment_reference")
            if (current_reference
                    and current_reference != payment.reference
                    and payment.status != Payment.STATUS_APPROVED):
                logger.info(f"Skipping Firebase sync for stale payment {payment.reference}")
                return

            self.firebase.update_data(path, {
                'payment_status': self.FIREBASE_PAYMENT_STATUS[payment.status],
                'payment_reference': payment.reference,
                'payment_updated_at': int(payment.updated_at.timestamp() * 1000),
            })
        except Exception as e:
            logger.error(f"Error syncing payment {payment.reference} to Firebase: {str(e)}")
            raise FirebaseSyncError(str(e)) from e

    @staticmethod
    def _raw_checksum(payload):
        try:
            return str(payload['signature']['checksum']).upper()[:64]
        except (KeyError, TypeError):
            return ''

    @staticmethod
    def _log_event(payment, event_type, payload, checksum, checksum_valid):
        PaymentEvent.objects.create(
            payment=payment,
            event_type=(event_type or 'unknown')[:50],
            payload=payload if isinstance(payload, (dict, list)) else {'raw': str(payload)},
            checksum=checksum,
            checksum_valid=checksum_valid,
        )


payment_service = PaymentService()
