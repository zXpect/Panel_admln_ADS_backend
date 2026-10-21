from urllib.parse import urlencode

from django.shortcuts import render
from django.views import View

from .common import is_valid_firebase_key

APP_PACKAGE = 'com.project.ads'


class PaymentReturnView(View):
    """
    GET /api/payments/return/?request_id=<id>&id=<transacción de Wompi>

    Wompi solo acepta una redirect-url https, no el deep link de la app. El
    checkout vuelve aquí y esta página abre adsapp://payment-result con el
    request_id. Solo lleva a la app (nunca a otro sitio). El resultado del pago
    no sale de esta página: la app lo lee de Firebase.
    """

    def get(self, request):
        request_id = request.GET.get('request_id', '')
        params = {'request_id': request_id} if is_valid_firebase_key(request_id) else {}
        query = urlencode(params)
        deep_link = f"adsapp://payment-result{'?' + query if query else ''}"
        # Chrome en Android abre la app con intent:// aunque el deep link directo se bloquee
        intent_link = (f"intent://payment-result{'?' + query if query else ''}"
                       f"#Intent;scheme=adsapp;package={APP_PACKAGE};end")
        return render(request, 'payments/payment_return.html', {
            'deep_link': deep_link,
            'intent_link': intent_link,
        })
