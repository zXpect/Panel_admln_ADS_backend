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
                title='Nueva Solicitud de Servicio',
                body=f"Tipo: {request.get('service_type', '')}\nDirección: {request.get('address', '')}",
                clientId=client_id or '',
            )
            return worker_id, data

        if notification_type == 'request_accepted':
            data.update(title='¡Solicitud Aceptada!', body=f"{worker_name} ha aceptado tu solicitud")
            return client_id, data

        if notification_type == 'request_rejected':
            body = 'Tu solicitud no pudo ser atendida'
            if request.get('rejection_reason'):
                body += f": {request['rejection_reason']}"
            data.update(title='Solicitud Rechazada', body=body)
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
        self.save_to_history(recipient, data)
        return self.send_to_user(recipient, data)

    # ---------- historial ----------

    def save_to_history(self, uid, data):
        """Guarda notifications/<uid>/<id> = {title, body, type, request_id, read, created_at}."""
        try:
            entry = {
                'title': data.get('title', ''),
                'body': data.get('body', ''),
                'type': data.get('type', ''),
                'request_id': data.get('requestId', ''),
                'read': False,
                'created_at': int(time.time() * 1000),
            }
            self.firebase.get_database_reference(f"{self.HISTORY_PATH}/{uid}").push().set(entry)
            return True
        except Exception as e:
            logger.error(f"Error saving notification history for {uid}: {str(e)}")
            return False

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
