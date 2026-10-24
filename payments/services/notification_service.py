import logging
import time
from datetime import datetime, timedelta, timezone

from firebase_admin import messaging

from worker_verification.services.firebase_service import firebase_service

logger = logging.getLogger(__name__)

COLOMBIA_TZ = timezone(timedelta(hours=-5))


class NotificationService:
    """
    Envía notificaciones push (FCM) desde el backend con el SDK admin, para que
    la app no necesite una credencial de servicio.

    El formato es el que ya procesa MyFirebaseMessagingService en la app:
    mensaje solo de datos con title, body, requestId y type.

    Cada notificación también se guarda en notifications/<uid>/<id> para la
    pantalla de notificaciones de la app (mockups 40 y 53), aunque el usuario
    no tenga token FCM. La app solo lee ese nodo y marca "read".

    Las notificaciones son de mejor esfuerzo: un fallo se registra en el log y
    no interrumpe la operación que la originó.
    """

    TOKENS_PATH = 'Tokens'
    HISTORY_PATH = 'notifications'

    STATUS_TEXTS = {
        'on_the_way': ('¡El trabajador va en camino!', 'El trabajador se dirige a tu ubicación'),
        'in_progress': ('Trabajo en progreso', 'El trabajador ha comenzado el servicio'),
        'completed': ('¡Trabajo completado!', 'El servicio ha sido completado. Realiza el pago y califica tu experiencia'),
    }

    def __init__(self):
        self.firebase = firebase_service

    # ---------- mensajes por tipo ----------

    def build_message(self, notification_type, request_id, request):
        """
        Arma (destinatario, datos) para un tipo de notificación a partir de la
        solicitud. El texto lo define el servidor, nunca la app.

        Returns:
            tuple: (uid_destinatario, dict) o (None, None) si el tipo no aplica
        """
        client_id = request.get('client_id')
        worker_id = request.get('worker_id')
        worker_name = request.get('worker_name') or 'El trabajador'
        data = {'requestId': request_id, 'type': notification_type}

        if notification_type == 'new_request':
            data.update(
                title='Nueva solicitud de servicio',
                body=f"Tipo: {request.get('service_type', '')}\nDirección: {request.get('address', '')}",
                clientId=client_id or '',
            )
            return worker_id, data

        if notification_type == 'request_accepted':
            data.update(title='¡Solicitud aceptada!', body=f"{worker_name} ha aceptado tu solicitud")
            return client_id, data

        if notification_type == 'request_rejected':
            body = 'Tu solicitud no pudo ser atendida'
            if request.get('rejection_reason'):
                body += f": {request['rejection_reason']}"
            data.update(title='Solicitud rechazada', body=body)
            return client_id, data

        if notification_type == 'status_change':
            status = request.get('status', '')
            title, body = self.STATUS_TEXTS.get(status, ('Actualización de solicitud', 'Tu solicitud ha sido actualizada'))
            data.update(title=title, body=body, status=status)
            return client_id, data

        if notification_type == 'quote_received':
            data.update(
                title='Nueva cotización',
                body=f"{worker_name} cotizó tu servicio en {format_cop(request.get('quoted_price', 0))}",
            )
            return client_id, data

        if notification_type == 'quote_accepted':
            data.update(title='Cotización aceptada', body='El cliente aceptó tu cotización. Ya puedes iniciar el servicio')
            return worker_id, data

        if notification_type == 'quote_rejected':
            data.update(title='Cotización rechazada', body='El cliente rechazó tu cotización. Puedes enviar una nueva')
            return worker_id, data

        if notification_type == 'request_rescheduled':
            data.update(
                title='Servicio reprogramado',
                body=f"{worker_name} cambió la hora de llegada al {format_schedule(request.get('scheduled_at'))}. "
                     'Si no te sirve, puedes cancelar la solicitud',
            )
            return client_id, data

        if notification_type == 'request_cancelled':
            # Se avisa a la otra parte
            if request.get('cancelled_by') == 'worker':
                data.update(title='Solicitud cancelada', body=f"{worker_name} canceló la solicitud")
                return client_id, data
            client_name = request.get('client_name') or 'El cliente'
            data.update(title='Solicitud cancelada', body=f"{client_name} canceló la solicitud")
            return worker_id, data

        if notification_type == 'requote_received':
            requote = request.get('requote') or {}
            data.update(
                title='Nuevo precio propuesto',
                body=f"{worker_name} propone cambiar el precio a {format_cop(requote.get('price', 0))}. "
                     'Acéptalo o recházalo; si lo rechazas, se mantiene el precio original',
            )
            return client_id, data

        if notification_type in ('requote_accepted', 'requote_rejected'):
            if notification_type == 'requote_accepted':
                data.update(title='Nuevo precio aceptado',
                            body=f"El cliente aceptó el nuevo precio de {format_cop(request.get('quoted_price', 0))}")
            else:
                data.update(title='Nuevo precio rechazado',
                            body=f"El cliente mantuvo el precio original de {format_cop(request.get('quoted_price', 0))}")
            return worker_id, data

        if notification_type == 'cash_received':
            data.update(
                title='Pago en efectivo registrado',
                body=f"{worker_name} registró que recibió {format_cop(request.get('quoted_price', 0))} en efectivo. "
                     'Si no estás de acuerdo, abre una PQR',
            )
            return client_id, data

        if notification_type == 'payment_approved':
            data.update(title='Pago recibido', body='El cliente pagó el servicio')
            return worker_id, data

        return None, None

    def notify(self, notification_type, request_id, request):
        recipient, data = self.build_message(notification_type, request_id, request)
        if not recipient:
            return False
        return self.deliver(recipient, data)

    def notify_reminder(self, kind, request_id, request):
        """
        Recordatorios de ReminderService (HU-17). kind:
        - service: servicio agendado próximo, a las dos partes (service_reminder)
        - quote: cotización sin responder, al cliente (quote_pending)
        - payment: servicio terminado sin pago; en efectivo se le recuerda al
          trabajador que lo registre, si no, al cliente que pague (payment_pending)
        """
        client_id = request.get('client_id')
        worker_id = request.get('worker_id')
        worker_name = request.get('worker_name') or 'El trabajador'
        base = {'requestId': request_id}

        if kind == 'service':
            hour = format_schedule(request.get('scheduled_at'))
            delivered = self.deliver(client_id, {
                **base, 'type': 'service_reminder', 'title': 'Tu servicio es pronto',
                'body': f"{worker_name} llega el {hour}"}) if client_id else False
            if worker_id:
                delivered = self.deliver(worker_id, {
                    **base, 'type': 'service_reminder', 'title': 'Tienes un servicio pronto',
                    'body': f"Servicio en {request.get('address', '')} el {hour}"}) or delivered
            return delivered

        if kind == 'quote':
            return bool(client_id) and self.deliver(client_id, {
                **base, 'type': 'quote_pending', 'title': 'Tienes una cotización sin responder',
                'body': f"{worker_name} cotizó tu servicio en {format_cop(request.get('quoted_price', 0))}. "
                        'Acéptala o recházala'})

        if kind == 'payment':
            if request.get('payment_method') == 'cash':
                return bool(worker_id) and self.deliver(worker_id, {
                    **base, 'type': 'payment_pending', 'title': 'Registra el pago en efectivo',
                    'body': 'Si ya recibiste el pago del servicio, márcalo como recibido'})
            return bool(client_id) and self.deliver(client_id, {
                **base, 'type': 'payment_pending', 'title': 'Tienes un pago pendiente',
                'body': f"Paga {format_cop(request.get('quoted_price', 0))} del servicio terminado y califícalo"})

        return False

    def notify_pqr_answered(self, pqr):
        """Avisa al autor que su PQR recibió respuesta (B11). Al tocarla, la app abre la solicitud."""
        type_name = dict(pqr.TYPES).get(pqr.type, 'PQR').lower()
        return self.deliver(pqr.author_uid, {
            'type': 'pqr_answered',
            'title': 'Tu PQR tiene respuesta',
            'body': f"Respondimos tu {type_name}. Ábrela para ver la respuesta",
            'requestId': pqr.service_request_id,
            'pqrId': str(pqr.id),
        })

    def deliver(self, uid, data):
        """
        Guarda la notificación en el historial y envía el push con la clave de
        esa entrada (notificationId), para que la app la marque como leída al abrirlo.
        """
        notification_id = self.save_to_history(uid, data)
        if notification_id:
            data = {**data, 'notificationId': notification_id}
        return self.send_to_user(uid, data)

    # ---------- historial ----------

    def save_to_history(self, uid, data):
        """
        Guarda notifications/<uid>/<id> = {title, body, type, request_id, read, created_at}.

        Returns:
            str: la clave <id> de la entrada, o None si no se pudo guardar
        """
        try:
            entry = {
                'title': data.get('title', ''),
                'body': data.get('body', ''),
                'type': data.get('type', ''),
                'request_id': data.get('requestId', ''),
                'read': False,
                'created_at': int(time.time() * 1000),
            }
            ref = self.firebase.get_database_reference(f"{self.HISTORY_PATH}/{uid}").push()
            ref.set(entry)
            return ref.key
        except Exception as e:
            logger.error(f"Error saving notification history for {uid}: {str(e)}")
            return None

    # ---------- envío ----------

    def send_to_user(self, uid, data):
        try:
            token = self.firebase.get_data(f"{self.TOKENS_PATH}/{uid}/token")
            if not token:
                logger.info(f"No FCM token for user {uid}")
                return False

            payload = {key: str(value) for key, value in data.items() if value is not None}
            payload.setdefault('timestamp', str(int(time.time() * 1000)))

            messaging.send(messaging.Message(
                token=token,
                data=payload,
                android=messaging.AndroidConfig(priority='high'),
            ))
            logger.info(f"Notification '{payload.get('type')}' sent to {uid}")
            return True
        except messaging.UnregisteredError:
            # Token caducado (la app se reinstaló o rotó el token): se borra para
            # no reintentar; la app guarda el nuevo al abrir o en onNewToken
            logger.warning(f"Stale FCM token for {uid}; removing it")
            try:
                self.firebase.delete_data(f"{self.TOKENS_PATH}/{uid}")
            except Exception as e:
                logger.error(f"Error removing stale token for {uid}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error sending notification to {uid}: {str(e)}")
            return False


def format_cop(value):
    try:
        return '$' + f"{int(value):,}".replace(',', '.')
    except (TypeError, ValueError):
        return '$0'


def format_schedule(timestamp_ms):
    """'15/10 a las 14:30' en hora de Colombia (UTC−5, sin horario de verano)."""
    try:
        moment = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=COLOMBIA_TZ)
    except (TypeError, ValueError, OverflowError, OSError):
        return 'nuevo horario'
    return moment.strftime('%d/%m a las %H:%M')


notification_service = NotificationService()
