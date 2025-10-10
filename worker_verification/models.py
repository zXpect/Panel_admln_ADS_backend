from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth.models import User


class VerificationLog(models.Model):
    """
    Modelo para registrar el historial de verificaciones de documentos
    """
    ACTIONS = (
        ('approved', 'Aprobado'),
        ('rejected', 'Rechazado'),
        ('pending', 'Pendiente'),
    )
    
    worker_id = models.CharField(max_length=255, verbose_name='ID del Trabajador')
    document_type = models.CharField(max_length=100, verbose_name='Tipo de Documento')
    action = models.CharField(max_length=20, choices=ACTIONS, verbose_name='Acción')
    reviewer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='Revisor')
    reason = models.TextField(blank=True, null=True, verbose_name='Razón')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de Creación')
    
    class Meta:
        verbose_name = 'Log de Verificación'
        verbose_name_plural = 'Logs de Verificación'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.worker_id} - {self.document_type} - {self.action}"


class SystemConfig(models.Model):
    """
    Modelo para configuraciones del sistema
    """
    key = models.CharField(max_length=100, unique=True, verbose_name='Clave')
    value = models.TextField(verbose_name='Valor')
    description = models.TextField(blank=True, verbose_name='Descripción')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Última Actualización')
    
    class Meta:
        verbose_name = 'Configuración del Sistema'
        verbose_name_plural = 'Configuraciones del Sistema'
    
    def __str__(self):
        return f"{self.key}: {self.value}"