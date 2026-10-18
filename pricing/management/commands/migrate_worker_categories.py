from django.core.management.base import BaseCommand

from worker_verification.services.firebase_service import firebase_service

from ...models import ServiceCategory
from ...services.worker_categories import as_list, legacy_work_to_category


class Command(BaseCommand):
    """
    Convierte el texto libre `work` de cada trabajador en `categories` (lista de
    slugs del catálogo), sin distinguir mayúsculas ni tildes (B3, D16;
    PLAN_CATALOGO_TAREAS.md §7). No toca a quien ya tiene `categories` ni borra
    `work`, que se conserva un sprint como respaldo. Los valores sin
    equivalencia (p. ej. Ferretería) se listan para revisión manual.

    Uso:
        python manage.py migrate_worker_categories --dry-run
        python manage.py migrate_worker_categories
    """
    help = 'Convierte User/Trabajadores/<uid>/work en categories'

    WORKERS_PATH = 'User/Trabajadores'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Solo muestra los cambios, no escribe')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        valid_slugs = set(ServiceCategory.objects.values_list('slug', flat=True))
        workers = firebase_service.get_data(self.WORKERS_PATH) or {}

        converted, skipped, manual = [], [], []
        for uid, worker in sorted(workers.items()):
            if not isinstance(worker, dict):
                continue
            name = worker.get('name') or uid
            if as_list(worker.get('categories')):
                skipped.append((uid, name))
                continue
            work = worker.get('work')
            slug = legacy_work_to_category(work, valid_slugs)
            if slug is None:
                manual.append((uid, name, work))
                continue
            converted.append((uid, name, work, slug))
            if not dry_run:
                firebase_service.update_data(f"{self.WORKERS_PATH}/{uid}", {'categories': [slug]})

        prefix = '[simulación] ' if dry_run else ''
        for uid, name, work, slug in converted:
            self.stdout.write(f"{prefix}{uid} ({name}): {work!r} -> ['{slug}']")
        for uid, name, work in manual:
            self.stdout.write(self.style.WARNING(f"REVISIÓN MANUAL {uid} ({name}): work={work!r} sin oficio equivalente"))
        self.stdout.write(
            f"{prefix}Convertidos: {len(converted)} · Ya tenían categories: {len(skipped)} · "
            f"Revisión manual: {len(manual)}")
