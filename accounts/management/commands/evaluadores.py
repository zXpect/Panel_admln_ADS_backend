"""
Cuentas de evaluador del panel (jurados): ver accounts/evaluators.py.

    python manage.py evaluadores crear jurado1 jurado2 --nombre "Jurado 1" --nombre "Jurado 2"
    python manage.py evaluadores restablecer jurado1
    python manage.py evaluadores listar
    python manage.py evaluadores desactivar

Las contraseñas se generan al azar y se muestran una sola vez: no quedan en ningún archivo.
"""
import secrets

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.evaluators import EVALUATOR_GROUP, access_until

# Sin letras ni números que se confundan al copiarlos a mano (0/O, 1/l/I)
ALPHABET = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def new_password():
    return '-'.join(''.join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(4))


class Command(BaseCommand):
    help = 'Crea, restablece, lista o desactiva las cuentas de evaluador (jurados) del panel.'

    def add_arguments(self, parser):
        parser.add_argument('accion', choices=['crear', 'restablecer', 'listar', 'desactivar'])
        parser.add_argument('usuarios', nargs='*', help='Nombres de usuario (crear / restablecer)')
        parser.add_argument('--nombre', action='append', default=[],
                            help='Nombre para mostrar de cada usuario, en el mismo orden')

    def handle(self, *args, accion, usuarios, nombre, **options):
        group, _ = Group.objects.get_or_create(name=EVALUATOR_GROUP)
        if accion in ('crear', 'restablecer') and not usuarios:
            raise CommandError('Indica al menos un nombre de usuario.')

        if accion == 'crear':
            self._print_credentials(self._create(group, usuarios, nombre))
        elif accion == 'restablecer':
            self._print_credentials(self._reset(group, usuarios))
        elif accion == 'listar':
            for user in group.user_set.order_by('username'):
                estado = 'activa' if user.is_active else 'desactivada'
                ultimo = user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else 'nunca'
                self.stdout.write(f'{user.username:<16} {user.first_name:<24} {estado:<12} último ingreso: {ultimo}')
            self.stdout.write(f'Acceso permitido hasta: {access_until().isoformat()}')
        else:
            count = group.user_set.filter(is_active=True).update(is_active=False)
            self.stdout.write(self.style.SUCCESS(f'{count} cuenta(s) de evaluador desactivada(s).'))

    @transaction.atomic
    def _create(self, group, usernames, names):
        taken = list(User.objects.filter(username__in=usernames).values_list('username', flat=True))
        if taken:
            raise CommandError(f'Ya existen: {", ".join(taken)}. Usa «restablecer» para darles otra contraseña.')
        created = []
        for i, username in enumerate(usernames):
            password = new_password()
            # Sin is_staff ni is_superuser: no entran al admin de Django
            user = User.objects.create_user(username, password=password,
                                            first_name=names[i] if i < len(names) else '')
            user.groups.add(group)
            created.append((user, password))
        return created

    @transaction.atomic
    def _reset(self, group, usernames):
        result = []
        for username in usernames:
            user = group.user_set.filter(username=username).first()
            if user is None:
                raise CommandError(f'«{username}» no es una cuenta de evaluador.')
            password = new_password()
            user.set_password(password)
            user.is_active = True
            user.save(update_fields=['password', 'is_active'])
            result.append((user, password))
        return result

    def _print_credentials(self, rows):
        self.stdout.write('')
        self.stdout.write('Copia estas credenciales ahora: no se vuelven a mostrar.')
        for user, password in rows:
            self.stdout.write(f'  usuario: {user.username:<16} contraseña: {password}')
        self.stdout.write(f'Acceso permitido hasta: {access_until().isoformat()}')
