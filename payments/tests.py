import copy
import hashlib

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from .guards import check_payment_mode
from .models import Payment
from .services.gateways.base import BaseGateway
from .services.signature import (
    event_checksum,
    integrity_signature,
    verify_event_checksum,
)

EVENTS_SECRET = 'test_events_secret'


def _sha256(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _build_event(status='APPROVED'):
    """Evento con la estructura documentada por Wompi, firmado con EVENTS_SECRET."""
    event = {
        'event': 'transaction.updated',
        'data': {
            'transaction': {
                'id': '1234-1610641025-49201',
                'amount_in_cents': 4490000,
                'reference': 'ADS-REF-001',
                'status': status,
            }
        },
        'environment': 'test',
        'signature': {
            'properties': ['transaction.id', 'transaction.status', 'transaction.amount_in_cents'],
            'checksum': '',
        },
        'timestamp': 1530291411,
        'sent_at': '2018-07-20T16:45:05.000Z',
    }
    event['signature']['checksum'] = event_checksum(event, EVENTS_SECRET)
    return event


class IntegritySignatureTests(SimpleTestCase):

    def test_concatenation_without_expiration(self):
        expected = _sha256('ADS-REF-0012990000COPsecret')
        self.assertEqual(integrity_signature('ADS-REF-001', 2990000, 'COP', 'secret'), expected)

    def test_expiration_goes_before_secret(self):
        expected = _sha256('ADS-REF-0012990000COP2026-10-06T15:00:00.000Zsecret')
        signature = integrity_signature(
            'ADS-REF-001', 2990000, 'COP', 'secret', expiration_time='2026-10-06T15:00:00.000Z'
        )
        self.assertEqual(signature, expected)

    def test_rejects_non_integer_amounts(self):
        for amount in (29900.5, '2990000', True, None):
            with self.assertRaises(ValueError):
                integrity_signature('ADS-REF-001', amount, 'COP', 'secret')

    def test_rejects_non_positive_amounts(self):
        for amount in (0, -100):
            with self.assertRaises(ValueError):
                integrity_signature('ADS-REF-001', amount, 'COP', 'secret')

    def test_rejects_missing_secret(self):
        with self.assertRaises(ValueError):
            integrity_signature('ADS-REF-001', 2990000, 'COP', '')


class EventChecksumTests(SimpleTestCase):

    def test_concatenation_matches_wompi_docs(self):
        # Regla documentada: valores de properties + timestamp + secreto
        event = _build_event()
        expected = _sha256('1234-1610641025-49201APPROVED44900001530291411' + EVENTS_SECRET).upper()
        self.assertEqual(event_checksum(event, EVENTS_SECRET), expected)

    def test_valid_event(self):
        self.assertTrue(verify_event_checksum(_build_event(), EVENTS_SECRET))

    def test_checksum_comparison_is_case_insensitive(self):
        event = _build_event()
        event['signature']['checksum'] = event['signature']['checksum'].lower()
        self.assertTrue(verify_event_checksum(event, EVENTS_SECRET))

    def test_wrong_secret(self):
        self.assertFalse(verify_event_checksum(_build_event(), 'otro_secreto'))

    def test_tampered_status(self):
        event = _build_event('DECLINED')
        event['data']['transaction']['status'] = 'APPROVED'
        self.assertFalse(verify_event_checksum(event, EVENTS_SECRET))

    def test_tampered_amount(self):
        event = _build_event()
        event['data']['transaction']['amount_in_cents'] = 100
        self.assertFalse(verify_event_checksum(event, EVENTS_SECRET))

    def test_header_must_match_when_present(self):
        event = _build_event()
        checksum = event['signature']['checksum']
        self.assertTrue(verify_event_checksum(event, EVENTS_SECRET, header_checksum=checksum))
        self.assertFalse(verify_event_checksum(event, EVENTS_SECRET, header_checksum='ABC'))

    def test_malformed_events_are_invalid(self):
        event = _build_event()
        missing_property = copy.deepcopy(event)
        missing_property['signature']['properties'].append('transaction.no_existe')
        no_timestamp = copy.deepcopy(event)
        del no_timestamp['timestamp']

        for malformed in ({}, None, missing_property, no_timestamp):
            self.assertFalse(verify_event_checksum(malformed, EVENTS_SECRET))


class _DummyGateway(BaseGateway):
    name = 'dummy'

    def create_transaction(self, reference, amount_in_cents, currency, redirect_url=None):
        raise NotImplementedError


class BaseGatewayTests(SimpleTestCase):

    def setUp(self):
        self.gateway = _DummyGateway('integrity', EVENTS_SECRET)

    def test_requires_secrets(self):
        with self.assertRaises(ValueError):
            _DummyGateway('', EVENTS_SECRET)

    def test_parse_event(self):
        event = self.gateway.parse_event(_build_event())
        self.assertEqual(event.reference, 'ADS-REF-001')
        self.assertEqual(event.status, 'APPROVED')
        self.assertEqual(event.amount_in_cents, 4490000)
        self.assertEqual(event.transaction_id, '1234-1610641025-49201')

    def test_parse_event_rejects_invalid_structure(self):
        with self.assertRaises(ValueError):
            self.gateway.parse_event({'event': 'transaction.updated', 'data': {}})

    def test_parse_event_rejects_float_amount(self):
        event = _build_event()
        event['data']['transaction']['amount_in_cents'] = 4490000.0
        with self.assertRaises(ValueError):
            self.gateway.parse_event(event)


class PaymentModeGuardTests(SimpleTestCase):

    def test_mock_forbidden_in_production(self):
        with self.assertRaises(ImproperlyConfigured):
            check_payment_mode('production', 'mock')

    def test_allowed_combinations(self):
        check_payment_mode('development', 'mock')
        check_payment_mode('development', 'wompi')
        check_payment_mode('production', 'wompi')

    def test_invalid_mode(self):
        with self.assertRaises(ImproperlyConfigured):
            check_payment_mode('development', 'paypal')


class PaymentTransitionTests(SimpleTestCase):

    def _payment(self, status):
        return Payment(status=status)

    def test_pending_can_be_resolved(self):
        payment = self._payment(Payment.STATUS_PENDING)
        for new_status in (Payment.STATUS_APPROVED, Payment.STATUS_DECLINED, Payment.STATUS_ERROR):
            self.assertTrue(payment.can_transition_to(new_status))

    def test_approved_only_can_be_voided(self):
        payment = self._payment(Payment.STATUS_APPROVED)
        self.assertTrue(payment.can_transition_to(Payment.STATUS_VOIDED))
        self.assertFalse(payment.can_transition_to(Payment.STATUS_PENDING))
        self.assertFalse(payment.can_transition_to(Payment.STATUS_DECLINED))

    def test_final_states_do_not_change(self):
        for status in (Payment.STATUS_DECLINED, Payment.STATUS_ERROR, Payment.STATUS_VOIDED):
            payment = self._payment(status)
            for new_status, _ in Payment.STATUSES:
                self.assertFalse(payment.can_transition_to(new_status))
