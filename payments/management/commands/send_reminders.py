from django.core.management.base import BaseCommand

from payments.services.reminder_service import reminder_service


class Command(BaseCommand):
    help = ('Envía los recordatorios de servicios agendados, cotizaciones sin responder y pagos '
            'pendientes (HU-17). Escribe en Firebase y envía push: es lo mismo que '
            'POST /api/internal/reminders/.')

    def handle(self, *args, **options):
        sent = reminder_service.run()
        self.stdout.write(
            f"Servicios: {sent['service']} · Cotizaciones: {sent['quote']} · Pagos: {sent['payment']}")
