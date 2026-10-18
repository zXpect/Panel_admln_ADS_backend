from ..models import VerificationLog


class AuditService:
    """
    Registra en VerificationLog cada decisión de verificación tomada desde el panel
    """

    # verificationStatus.status del trabajador -> VerificationLog.action
    WORKER_STATUS_ACTIONS = {
        'approved': 'approved',
        'rejected': 'rejected',
        'documents_submitted': 'pending',
    }

    WORKER_STATUS_DOCUMENT_TYPE = 'verificationStatus'

    @staticmethod
    def reviewer_label(user):
        """Valor que se escribe en `reviewedBy` de Firebase para el revisor autenticado"""
        return user.get_username()

    @staticmethod
    def document_type(category, subcategory=None):
        """`category` o `category/subcategory`, como en la ruta de WorkerDocuments"""
        return f"{category}/{subcategory}" if subcategory else category

    def log_document_decision(self, reviewer, worker_id, category, subcategory, action, reason=None):
        return VerificationLog.objects.create(
            worker_id=worker_id,
            document_type=self.document_type(category, subcategory),
            action=action,
            reviewer=reviewer,
            reason=reason,
        )

    def log_worker_status_change(self, reviewer, worker_id, new_status):
        return VerificationLog.objects.create(
            worker_id=worker_id,
            document_type=self.WORKER_STATUS_DOCUMENT_TYPE,
            action=self.WORKER_STATUS_ACTIONS[new_status],
            reviewer=reviewer,
        )


# Instancia singleton
audit_service = AuditService()
