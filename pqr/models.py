from django.contrib.auth.models import User
from django.db import models


class PQR(models.Model):
    """
    Petición, queja o reclamo sobre una solicitud (B11, D21). Vive en SQL y
    no en Firebase para conservar la auditoría: no se borra, se cierra.
    El plazo de respuesta (due_at) es de 15 días hábiles, calculado en el servidor.
    """
    TYPE_PETITION = 'peticion'
    TYPE_COMPLAINT = 'queja'
    TYPE_CLAIM = 'reclamo'
    TYPES = (
        (TYPE_PETITION, 'Petición'),
        (TYPE_COMPLAINT, 'Queja'),
        (TYPE_CLAIM, 'Reclamo'),
    )

    STATUS_OPEN = 'abierta'
    STATUS_IN_PROGRESS = 'en_tramite'
    STATUS_CLOSED = 'cerrada'
    STATUSES = (
        (STATUS_OPEN, 'Abierta'),
        (STATUS_IN_PROGRESS, 'En trámite'),
        (STATUS_CLOSED, 'Cerrada'),
    )

    ROLE_CLIENT = 'client'
    ROLE_WORKER = 'worker'
    ROLES = (
        (ROLE_CLIENT, 'Cliente'),
        (ROLE_WORKER, 'Trabajador'),
    )

    service_request_id = models.CharField(max_length=255, db_index=True, verbose_name='ID de la Solicitud')
    author_uid = models.CharField(max_length=128, db_index=True, verbose_name='UID del Autor')
    author_role = models.CharField(max_length=10, choices=ROLES, verbose_name='Rol del Autor')
    type = models.CharField(max_length=10, choices=TYPES, verbose_name='Tipo')
    description = models.TextField(verbose_name='Descripción')
    status = models.CharField(max_length=12, choices=STATUSES, default=STATUS_OPEN, db_index=True,
                              verbose_name='Estado')
    response = models.TextField(null=True, blank=True, verbose_name='Respuesta')
    responded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT,
                                     verbose_name='Respondida por')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de Registro')
    due_at = models.DateTimeField(verbose_name='Fecha Límite de Respuesta')
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name='Fecha de Cierre')

    class Meta:
        db_table = 'pqr'
        verbose_name = 'PQR'
        verbose_name_plural = 'PQR'
        ordering = ['-created_at']

    def __str__(self):
        return f"PQR {self.id} - {self.type} - {self.status}"
