from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'payments'
    verbose_name = 'Pagos'

    def ready(self):
        # Se valida al arrancar (runserver, gunicorn, manage.py) y no solo
        # en los system checks, que gunicorn no ejecuta.
        from django.conf import settings
        from .guards import check_payment_mode

        check_payment_mode(settings.DJANGO_ENV, settings.PAYMENTS['MODE'])
