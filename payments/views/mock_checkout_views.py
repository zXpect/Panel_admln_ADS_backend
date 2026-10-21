from urllib.parse import urlencode, urlparse

from django.conf import settings
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.views import View

from ..models import Payment
from ..services.gateways import get_gateway
from ..services.payment_service import FirebaseSyncError, payment_service
import logging

logger = logging.getLogger(__name__)

OUTCOMES = {
    'approved': Payment.STATUS_APPROVED,
    'declined': Payment.STATUS_DECLINED,
    'error': Payment.STATUS_ERROR,
}


class AppRedirect(HttpResponseRedirect):
    # Además de http/https permite volver a la app por deep link (adsapp://...)
    allowed_schemes = ['http', 'https', 'adsapp']


def _is_allowed_redirect(url):
    # Vacío = sin redirección (se muestra el resultado en la página)
    return not url or urlparse(url).scheme in AppRedirect.allowed_schemes


def _format_cop(amount_in_cents):
    return '$' + f"{amount_in_cents // 100:,}".replace(',', '.')


class MockCheckoutView(View):
    """
    GET/POST /api/payments/mock-checkout/<reference>/

    Imita el Web Checkout de Wompi: valida la firma de integridad del enlace,
    muestra el resumen y permite simular el resultado. Al elegir, genera un
    evento 'transaction.updated' firmado, lo procesa por el mismo camino que
    el webhook y redirige a redirect-url con ?id=<transacción>, como Wompi.

    Solo existe con PAGOS_MODO=mock (en otro modo responde 404).
    """
    template_name = 'payments/mock_checkout.html'

    def _get_context(self, request, reference):
        if settings.PAYMENTS['MODE'] != 'mock':
            raise Http404

        gateway = get_gateway()
        payment = Payment.objects.filter(reference=reference).first()
        if payment is None:
            raise Http404

        params = request.GET if request.method == 'GET' else request.POST
        signature = params.get('signature:integrity', '')
        redirect_url = params.get('redirect-url', '')

        try:
            amount_in_cents = int(params.get('amount-in-cents', ''))
        except ValueError:
            amount_in_cents = None

        # El enlace se valida completo antes de procesar nada: un redirect-url
        # no permitido no debe dejar un pago aprobado a medias.
        link_valid = (
            _is_allowed_redirect(redirect_url)
            and amount_in_cents == payment.amount_in_cents
            and params.get('currency') == payment.currency
            and gateway.verify_integrity(reference, amount_in_cents, payment.currency, signature)
        )

        return gateway, payment, {
            'payment': payment,
            'amount_display': _format_cop(payment.amount_in_cents),
            'link_valid': link_valid,
            'is_pending': payment.status == Payment.STATUS_PENDING,
            'params': {
                'amount-in-cents': params.get('amount-in-cents', ''),
                'currency': params.get('currency', ''),
                'signature:integrity': signature,
                'redirect-url': redirect_url,
            },
            'redirect_url': redirect_url,
        }

    def get(self, request, reference):
        _, _, context = self._get_context(request, reference)
        status_code = 200 if context['link_valid'] else 400
        return render(request, self.template_name, context, status=status_code)

    def post(self, request, reference):
        gateway, payment, context = self._get_context(request, reference)

        outcome = OUTCOMES.get(request.POST.get('outcome'))
        if not context['link_valid'] or outcome is None:
            return render(request, self.template_name, context, status=400)

        if not context['is_pending']:
            return render(request, self.template_name, context, status=409)

        transaction_id = gateway.new_transaction_id()
        event = gateway.build_event(
            reference=payment.reference,
            transaction_id=transaction_id,
            status=outcome,
            amount_in_cents=payment.amount_in_cents,
            currency=payment.currency,
            redirect_url=context['redirect_url'] or None,
        )

        try:
            payment_service.process_event(event, header_checksum=event['signature']['checksum'])
        except FirebaseSyncError:
            # El pago quedó guardado; la app lo verá al reintentar o por el detalle del pago
            logger.error(f"Mock checkout: Firebase sync failed for {payment.reference}")

        payment.refresh_from_db()

        if context['redirect_url']:
            separator = '&' if '?' in context['redirect_url'] else '?'
            query = urlencode({'id': transaction_id, 'env': 'test'})
            return AppRedirect(f"{context['redirect_url']}{separator}{query}")

        context.update({'payment': payment, 'is_pending': False, 'finished': True})
        return render(request, self.template_name, context)
