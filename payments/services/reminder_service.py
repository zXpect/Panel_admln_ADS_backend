import logging
import time

from worker_verification.services.firebase_service import firebase_service

from .notification_service import notification_service

logger = logging.getLogger(__name__)

MINUTE_MS = 60 * 1000
HOUR_MS = 60 * MINUTE_MS


class ReminderService:
    """
    Recordatorios y avisos de pendientes (HU-17): servicio agendado próximo,
    cotización sin responder y pago pendiente de un servicio terminado.

    No hay tareas programadas en el plan gratuito de Render: un programador
    externo llama POST /api/internal/reminders/ cada 30 minutos (ver
    .github/workflows/reminders.yml) o se corre `manage.py send_reminders`.
    Cada recordatorio sale una sola vez: la solicitud guarda en reminder_*_at el
    valor que lo originó (scheduled_at, quoted_at o completed_at), así que si el
    servicio se reprograma o se vuelve a cotizar, se recuerda otra vez.
    """

    REQUESTS_PATH = 'requests'

    # Con el programador cada 30 min, el aviso llega entre 1,5 y 2 horas antes
    SERVICE_LEAD_MS = 2 * HOUR_MS
    QUOTE_WAIT_MS = 12 * HOUR_MS
    PAYMENT_WAIT_MS = 1 * HOUR_MS

    def __init__(self):
        self.firebase = firebase_service
        self.notifications = notification_service

    def _by_status(self, status):
        results = self.firebase.query_data(self.REQUESTS_PATH, order_by='status', equal_to=status) or {}
        return [(request_id, request) for request_id, request in results.items() if isinstance(request, dict)]

    @staticmethod
    def _ms(value):
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else None

    def _send(self, kind, marker, value, request_id, request):
        # Primero la marca: si dos ejecuciones coinciden, la segunda ya no lo envía
        self.firebase.update_data(f"{self.REQUESTS_PATH}/{request_id}", {marker: value})
        self.notifications.notify_reminder(kind, request_id, request)

    def run(self, now=None):
        """
        Envía los recordatorios que tocan.

        Returns:
            dict: cuántos se enviaron de cada tipo
        """
        now = now if now is not None else int(time.time() * 1000)
        sent = {'service': 0, 'quote': 0, 'payment': 0}

        for request_id, request in self._by_status('accepted'):
            scheduled_at = self._ms(request.get('scheduled_at'))
            if (request.get('quote_status') == 'accepted' and scheduled_at
                    and now < scheduled_at <= now + self.SERVICE_LEAD_MS
                    and request.get('reminder_service_at') != scheduled_at):
                self._send('service', 'reminder_service_at', scheduled_at, request_id, request)
                sent['service'] += 1

            quoted_at = self._ms(request.get('quoted_at'))
            if (request.get('quote_status') == 'quoted' and quoted_at
                    and now - quoted_at >= self.QUOTE_WAIT_MS
                    and request.get('reminder_quote_at') != quoted_at):
                self._send('quote', 'reminder_quote_at', quoted_at, request_id, request)
                sent['quote'] += 1

        for request_id, request in self._by_status('completed'):
            completed_at = self._ms(request.get('completed_at'))
            if (request.get('payment_status') != 'approved' and completed_at
                    and now - completed_at >= self.PAYMENT_WAIT_MS
                    and request.get('reminder_payment_at') != completed_at):
                self._send('payment', 'reminder_payment_at', completed_at, request_id, request)
                sent['payment'] += 1

        if any(sent.values()):
            logger.info(f"Reminders sent: {sent}")
        return sent


reminder_service = ReminderService()
