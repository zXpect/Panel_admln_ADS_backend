"""
Fecha de creación de las cuentas, tomada de Firebase Authentication.

Los nodos que escribe la app no guardan una fecha de registro fija (el cliente no
tiene fecha y el `timestamp` del trabajador cambia con su actividad), así que el
panel ordena por la fecha en que se creó la cuenta en Auth.
"""
import logging

from django.core.cache import cache
from firebase_admin import auth as firebase_auth

logger = logging.getLogger(__name__)

CACHE_KEY = 'auth_creation_times'
CACHE_SECONDS = 60


def creation_times():
    """{uid: milisegundos de creación}; vacío si Auth no responde (el listado no falla por esto)."""
    times = cache.get(CACHE_KEY)
    if times is None:
        try:
            times = {user.uid: user.user_metadata.creation_timestamp
                     for user in firebase_auth.list_users().iterate_all()}
        except Exception as e:
            logger.warning(f"No se pudieron leer las fechas de creación de Auth: {e}")
            return {}
        cache.set(CACHE_KEY, times, CACHE_SECONDS)
    return times


def attach_created_at(accounts):
    """Agrega `createdAt` (ms o None) a cada cuenta de la lista, por su `id`."""
    times = creation_times()
    for account in accounts:
        account['createdAt'] = times.get(account.get('id'))
    return accounts
