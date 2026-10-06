import logging
import time

from firebase_admin import messaging

from worker_verification.services.firebase_service import firebase_service

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Envía notificaciones push (FCM) desde el backend con el SDK admin, para que
    la app no necesite una credencial de servicio.

    El formato es el que ya procesa MyFirebaseMessagingService en la app:
    mensaje solo de datos con title, body, requestId y type.

    Las notificaciones son de mejor esfuerzo: un fallo se registra en el log y
    no interrumpe la operación que la originó.
    """

    TOKENS_PATH = 'Tokens'

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

        if notification_type == 'payment_approved':
            data.update(title='Pago recibido', body='El cliente pagó el servicio')
            return worker_id, data

        return None, None

    def notify(self, notification_type, request_id, request):
        recipient, data = self.build_message(notification_type, request_id, request)
        if not recipient:
            return False
        return self.send_to_user(recipient, data)

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


notification_service = NotificationService()
