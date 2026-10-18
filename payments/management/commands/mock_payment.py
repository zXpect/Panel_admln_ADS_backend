from django.core.management.base import BaseCommand, CommandError

from payments.services.payment_service import payment_service


class Command(BaseCommand):
    """
    Crea un pago PENDING e imprime la URL del checkout (para pruebas manuales
    mientras no existe POST /api/payments/). Escribe payment_status y
    payment_reference en requests/<request_id> de Firebase.

    Uso:
        python manage.py mock_payment <request_id> <monto_cop> [--client X --worker Y --redirect URL]
    """
    help = 'Crea un pago de prueba e imprime la URL del checkout'

    def add_arguments(self, parser):
        parser.add_argument('request_id')
        parser.add_argument('amount_cop', type=int, help='Monto en pesos COP (entero)')
        parser.add_argument('--client', default='test-client')
        parser.add_argument('--worker', default='test-worker')
        parser.add_argument('--redirect', default=None)

    def handle(self, *args, **options):
        if options['amount_cop'] <= 0:
            raise CommandError('El monto debe ser mayor que cero')

        payment, session = payment_service.create_payment(
            service_request_id=options['request_id'],
            client_uid=options['client'],
            worker_uid=options['worker'],
            amount_in_cents=options['amount_cop'] * 100,
            redirect_url=options['redirect'],
        )
        self.stdout.write(f"Referencia: {payment.reference}")
        self.stdout.write(f"Checkout:   {session.checkout_url}")
