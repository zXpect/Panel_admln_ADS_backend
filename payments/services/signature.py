"""
Firmas de Wompi (funciones puras, sin acceso a settings ni a la BD).

Las usan tanto MockGateway como WompiGateway: el mock produce y valida
exactamente las mismas estructuras, solo cambian los secretos.

Referencias:
- Firma de integridad: https://docs.wompi.co/docs/colombia/widget-checkout-web/
- Checksum de eventos: https://docs.wompi.co/docs/colombia/eventos/
"""
import hashlib
import hmac


def _sha256_hex(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def integrity_signature(reference, amount_in_cents, currency, integrity_secret, expiration_time=None):
    """
    SHA256 de: reference + amount_in_cents + currency [+ expiration_time] + integrity_secret

    Args:
        reference (str): Referencia única del pago
        amount_in_cents (int): Monto en centavos (entero)
        currency (str): Moneda, p. ej. 'COP'
        integrity_secret (str): Secreto de integridad
        expiration_time (str, opcional): Fecha ISO 8601; va antes del secreto

    Returns:
        str: Hash hexadecimal en minúsculas
    """
    # bool es subclase de int: se rechaza explícitamente
    if not isinstance(amount_in_cents, int) or isinstance(amount_in_cents, bool):
        raise ValueError('amount_in_cents debe ser un entero')
    if amount_in_cents <= 0:
        raise ValueError('amount_in_cents debe ser mayor que cero')
    if not reference or not currency or not integrity_secret:
        raise ValueError('reference, currency e integrity_secret son obligatorios')

    parts = [reference, str(amount_in_cents), currency]
    if expiration_time:
        parts.append(expiration_time)
    parts.append(integrity_secret)
    return _sha256_hex(''.join(parts))


def _resolve_property(data, path):
    """Resuelve una ruta con puntos (p. ej. 'transaction.id') dentro de data."""
    value = data
    for key in path.split('.'):
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"Propiedad '{path}' no encontrada en el evento")
        value = value[key]
    return value


def event_checksum(event, events_secret):
    """
    SHA256 de: valores de signature.properties (en orden, resueltos dentro de
    'data') + timestamp + events_secret.

    Returns:
        str: Hash hexadecimal en mayúsculas (como lo envía Wompi)
    """
    if not events_secret:
        raise ValueError('events_secret es obligatorio')

    try:
        properties = event['signature']['properties']
        data = event['data']
        timestamp = event['timestamp']
    except (KeyError, TypeError):
        raise ValueError('Evento sin signature.properties, data o timestamp')

    values = [str(_resolve_property(data, path)) for path in properties]
    concatenated = ''.join(values) + str(timestamp) + events_secret
    return _sha256_hex(concatenated).upper()


def verify_event_checksum(event, events_secret, header_checksum=None):
    """
    Valida el checksum de un evento contra signature.checksum y, si viene,
    contra el header X-Event-Checksum. Comparación en tiempo constante.

    Returns:
        bool: True si el checksum es válido
    """
    try:
        expected = event_checksum(event, events_secret)
        received = str(event['signature']['checksum']).upper()
    except (ValueError, KeyError, TypeError):
        return False

    if not hmac.compare_digest(expected, received):
        return False
    if header_checksum is not None and not hmac.compare_digest(expected, str(header_checksum).upper()):
        return False
    return True
