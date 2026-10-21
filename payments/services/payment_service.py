import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from worker_verification.services.firebase_service import firebase_service

from ..models import Payment, PaymentEvent
from .gateways import get_gateway
from .notification_service import notification_service
from .service_request_service import ServiceRequestError, service_request_service

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

    # Un pago PENDING más viejo que esto se da por abandonado y se permite reintentar
    PENDING_EXPIRATION = timedelta(minutes=30)

    def __init__(self):
        self.firebase = firebase_service
        self.requests = service_request_service
        self.notifications = notification_service

    @staticmethod
    def generate_reference():
        return f"ADS-{uuid.uuid4().hex[:20].upper()}"

    def create_payment(self, service_request_id, client_uid, worker_uid, amount_in_cents, redirect_url=None, sync=True):
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

        if sync:
            self.sync_to_firebase(payment)
        return payment, session

    def start_payment(self, client_uid, service_request_id, redirect_url=None):
        """
        Inicia (o retoma) el pago de una solicitud. El monto sale de la
        cotización aceptada guardada en Firebase, nunca de la app.

        Returns:
            tuple: (Payment, CheckoutSession, created)

        Raises:
            ServiceRequestError: la solicitud no se puede pagar (403/404/409)
        """
        request = self.requests.get_request(service_request_id)

        if request.get('client_id') != client_uid:
            raise ServiceRequestError('Solo el cliente de la solicitud puede pagarla', 403)
        if request.get('status') != 'completed':
            raise ServiceRequestError('El servicio debe estar completado para pagarlo', 409)
        if request.get('quote_status') != 'accepted':
            raise ServiceRequestError('La solicitud no tiene una cotización aceptada', 409)
        if request.get('payment_status') == 'approved':
            raise ServiceRequestError('Esta solicitud ya fue pagada', 409)
        if request.get('payment_method') == self.requests.PAYMENT_CASH:
            raise ServiceRequestError('El método de pago de esta solicitud es efectivo', 409)

        quoted_price = request.get('quoted_price')
        if not isinstance(quoted_price, int) or isinstance(quoted_price, bool) or quoted_price <= 0:
            logger.error(f"Invalid quoted_price for request {service_request_id}")
            raise ServiceRequestError('La cotización de la solicitud no es válida', 409)
        amount_in_cents = quoted_price * 100

        if Payment.objects.filter(service_request_id=service_request_id, status=Payment.STATUS_APPROVED).exists():
            raise ServiceRequestError('Esta solicitud ya fue pagada', 409)

        pending = self._reusable_pending_payment(service_request_id, amount_in_cents)
        if pending is not None and pending.status == Payment.STATUS_APPROVED:
            # La pasarela lo aprobó y el evento no había llegado
            raise ServiceRequestError('Esta solicitud ya fue pagada', 409)
        if pending:
            session = get_gateway().create_transaction(
                pending.reference, pending.amount_in_cents, pending.currency, redirect_url)
            return pending, session, False

        try:
            with transaction.atomic():
                payment, session = self.create_payment(
                    service_request_id=service_request_id,
                    client_uid=client_uid,
                    worker_uid=request.get('worker_id', ''),
                    amount_in_cents=amount_in_cents,
                    redirect_url=redirect_url,
                    sync=False,
                )
        except IntegrityError:
            # Otra petición simultánea creó el pago PENDING; se devuelve ese
            pending = Payment.objects.get(service_request_id=service_request_id, status=Payment.STATUS_PENDING)
            session = get_gateway().create_transaction(
                pending.reference, pending.amount_in_cents, pending.currency, redirect_url)
            return pending, session, False

        try:
            self.sync_to_firebase(payment)
        except FirebaseSyncError:
            # El pago existe y el checkout funciona; el webhook vuelve a sincronizar
            pass
        return payment, session, True

    def register_cash_payment(self, worker_uid, service_request_id):
        """
        «Recibí el pago» del trabajador en un servicio en efectivo (D10). Crea un
        Payment APPROVED con gateway 'cash', sin pasar por la pasarela, para que
        el libro de pagos tenga todos los servicios pagados, y lo refleja en la
        solicitud. El cliente recibe un aviso y, si no está de acuerdo, abre una PQR.

        Returns:
            tuple: (Payment, solicitud actualizada)
        """
        request = self.requests.get_request(service_request_id)
        self.requests.check_cash_payment(request, worker_uid)
        quoted_price = request.get('quoted_price')
        if not isinstance(quoted_price, int) or isinstance(quoted_price, bool) or quoted_price <= 0:
            raise ServiceRequestError('La cotización de la solicitud no es válida', 409)
        if Payment.objects.filter(service_request_id=service_request_id, status=Payment.STATUS_APPROVED).exists():
            raise ServiceRequestError('El pago de esta solicitud ya está registrado', 409)

        with transaction.atomic():
            payment = Payment.objects.create(
                reference=self.generate_reference(),
                service_request_id=service_request_id,
                client_uid=request.get('client_id', ''),
                worker_uid=worker_uid,
                amount_in_cents=quoted_price * 100,
                currency=settings.PAYMENTS['CURRENCY'],
                status=Payment.STATUS_APPROVED,
                gateway=Payment.GATEWAY_CASH,
            )
            now = int(payment.created_at.timestamp() * 1000)

            def update(current):
                # Se repiten las validaciones dentro de la transacción de Firebase
                self.requests.check_cash_payment(current, worker_uid)
                current['payment_status'] = 'approved'
                current['payment_reference'] = payment.reference
                current['payment_updated_at'] = now
                current['cash_received_at'] = now
                current['last_updated'] = now

            # Si Firebase rechaza el cambio, el Payment se revierte con la transacción SQL
            updated = self.requests._transact_request(service_request_id, update)

        logger.info(f"Cash payment {payment.reference} registered for request {service_request_id}")
        self.notifications.notify('cash_received', service_request_id, updated)
        return payment, updated

    def _reusable_pending_payment(self, service_request_id, amount_in_cents):
        """
        Devuelve el pago PENDING vigente de la solicitud, o None. Uno vencido
        (más de PENDING_EXPIRATION) o con otro monto se cierra como ERROR.

        Antes de cerrarlo se consulta la pasarela: si la transacción ya terminó
        se aplica ese estado (y si quedó APPROVED se devuelve el pago aprobado);
        si sigue en proceso en la pasarela y el monto no cambió, se reutiliza.
        """
        pending = Payment.objects.filter(
            service_request_id=service_request_id, status=Payment.STATUS_PENDING).first()
        if pending is None:
            return None

        expired = pending.created_at < timezone.now() - self.PENDING_EXPIRATION
        if not expired and pending.amount_in_cents == amount_in_cents:
            return pending

        found = get_gateway().find_transaction(pending.reference)
        if found is not None:
            if found.status in self.FINAL_GATEWAY_STATUSES and found.amount_in_cents == pending.amount_in_cents:
                return self._reconcile(pending, found)
            if found.status == Payment.STATUS_PENDING and pending.amount_in_cents == amount_in_cents:
                return pending

        reason = 'expired' if expired else 'amount_changed'
        logger.info(f"Closing pending payment {pending.reference}: {reason}")
        pending.status = Payment.STATUS_ERROR
        pending.save(update_fields=['status', 'updated_at'])
        PaymentEvent.objects.create(
            payment=pending,
            event_type=f'local.{reason}',
            payload={'reason': reason},
            checksum='',
            checksum_valid=True,
        )
        return None

    def _reconcile(self, payment, found):
        """
        Aplica a un pago PENDING el estado final consultado en la pasarela
        (el evento se perdió o aún no llega).

        Returns:
            Payment si quedó APPROVED; None si quedó cerrado sin cobro
        """
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=payment.pk)
            if payment.status != Payment.STATUS_PENDING or not payment.can_transition_to(found.status):
                return None
            logger.info(f"Payment {payment.reference} reconciled with gateway: {found.status}")
            payment.status = found.status
            payment.gateway_transaction_id = found.transaction_id
            payment.save(update_fields=['status', 'gateway_transaction_id', 'updated_at'])
            PaymentEvent.objects.create(
                payment=payment,
                event_type='local.reconciled',
                payload={'status': found.status, 'transaction_id': found.transaction_id,
                         'amount_in_cents': found.amount_in_cents},
                checksum='',
                checksum_valid=True,
            )

        try:
            self.sync_to_firebase(payment)
        except FirebaseSyncError:
            pass
        if payment.status == Payment.STATUS_APPROVED:
            self.notifications.notify('payment_approved', payment.service_request_id, {
                'worker_id': payment.worker_uid,
            })
            return payment
        return None

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

        if result.outcome == EventResult.APPLIED and payment.status == Payment.STATUS_APPROVED:
            self.notifications.notify('payment_approved', payment.service_request_id, {
                'worker_id': payment.worker_uid,
            })
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
