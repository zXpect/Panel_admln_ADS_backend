"""
Genera las reglas de Realtime Database de ADS.

Las expresiones de las reglas son largas y difíciles de mantener a mano en
JSON; este script es la fuente de verdad. No editar los .json directamente.

Uso (desde backend/firebase/):
    python build_rules.py

Genera:
- database.rules.json         Reglas finales: cotización, pagos, calificación y
                              notificaciones pasan por el backend (fases 3 y 4).
- database.rules.stage1.json  Etapa 1: para la app actual, que aún califica y
                              envía notificaciones por su cuenta. No exige
                              cotización para iniciar el viaje ni pago para
                              calificar, y conserva las excepciones interinas
                              (rating del trabajador escrito por el cliente,
                              lectura de Tokens ajenos).
"""
import json
import os

AUTH = "auth != null"

# Campos de requests/<id> que solo escribe el backend (SDK admin)
PROTECTED_REQUEST_FIELDS = [
    'quoted_price',
    'quote_status',
    'quoted_at',
    'quote_accepted_at',
    'quote_rejection_reason',
    'payment_status',
    'payment_reference',
    'payment_updated_at',
]

# Calificación: en las reglas finales la registra el backend
# (POST /api/requests/<id>/rating/), que también recalcula el promedio
RATING_FIELDS = ['is_rated', 'client_rating', 'client_comment', 'rated_at']


def AND(*parts):
    return '(' + ' && '.join(parts) + ')'


def OR(*parts):
    return '(' + ' || '.join(parts) + ')'


def d(field):
    return f"data.child('{field}').val()"


def n(field):
    return f"newData.child('{field}').val()"


def unchanged(field):
    return f"{n(field)} == {d(field)}"


def status_change(old, new):
    return f"({d('status')} == '{old}' && {n('status')} == '{new}')"


def build_requests(stage1):
    quote_gate = () if stage1 else (f"{d('quote_status')} == 'accepted'",)

    create = AND(
        "!data.exists()",
        f"{n('client_id')} == auth.uid",
        "newData.child('worker_id').isString()",
        f"{n('status')} == 'pending'",
        *[f"!newData.child('{field}').exists()" for field in PROTECTED_REQUEST_FIELDS],
        f"{n('is_rated')} != true",
        "!newData.child('client_rating').exists()",
    )

    if stage1:
        # La app actual califica escribiendo directamente en la solicitud
        client_rating_rule = AND(
            OR(f"{n('is_rated')} != true", f"{d('is_rated')} == true", f"{d('status')} == 'completed'"),
            OR(f"{d('is_rated')} != true", AND(unchanged('client_rating'), unchanged('client_comment'))),
        )
    else:
        client_rating_rule = AND(*[unchanged(field) for field in RATING_FIELDS])

    client_update = AND(
        f"auth.uid == {d('client_id')}",
        # Cancela mientras no haya precio acordado: en 'pending', o en 'accepted'
        # con la cotización pendiente o rechazada
        OR(unchanged('status'),
           status_change('pending', 'cancelled'),
           AND(status_change('accepted', 'cancelled'), f"{d('quote_status')} != 'accepted'")),
        client_rating_rule,
    )

    worker_update = AND(
        f"auth.uid == {d('worker_id')}",
        OR(
            unchanged('status'),
            status_change('pending', 'accepted'),
            status_change('pending', 'rejected'),
            AND(status_change('accepted', 'on_the_way'), *quote_gate),
            status_change('on_the_way', 'in_progress'),
            status_change('in_progress', 'completed'),
        ),
        *[unchanged(field) for field in RATING_FIELDS],
    )

    update = AND(
        "data.exists()",
        unchanged('client_id'), unchanged('worker_id'),
        *[unchanged(field) for field in PROTECTED_REQUEST_FIELDS],
        OR(client_update, worker_update),
    )

    return {
        ".indexOn": ["client_id", "worker_id"],
        # Las listas solo se leen con consulta filtrada por el propio uid
        ".read": AND(AUTH,
                     OR("query.orderByChild == 'client_id'", "query.orderByChild == 'worker_id'"),
                     "query.equalTo == auth.uid"),
        "$requestId": {
            ".read": AND(AUTH, OR(f"{d('client_id')} == auth.uid", f"{d('worker_id')} == auth.uid")),
            ".write": AND(AUTH, "newData.exists()", OR(create, update)),
        },
    }


def build_workers(stage1):
    owner = AND(
        AUTH, "auth.uid == $uid", "newData.exists()",
        # rating/totalRatings: 0 al registrarse; después el propio trabajador no los toca
        OR(AND("data.exists()", unchanged('rating'), unchanged('totalRatings')),
           AND("!data.exists()",
               OR(f"{n('rating')} == null", f"{n('rating')} == 0"),
               OR(f"{n('totalRatings')} == null", f"{n('totalRatings')} == 0"))),
        unchanged('isActive'),
        # Solo el panel admin aprueba o rechaza; el trabajador solo puede enviar documentos
        OR("newData.child('verificationStatus').child('status').val() == "
           "data.child('verificationStatus').child('status').val()",
           "newData.child('verificationStatus').child('status').val() == 'documents_submitted'"),
    )
    worker = {".write": owner}

    if stage1:
        # Interino: la app actual actualiza el promedio desde el teléfono del
        # cliente (RequestProvider.rateRequest). En las reglas finales lo hace el backend.
        other_user = AND(AUTH, "auth.uid != $uid", "data.parent().exists()")
        worker.update({
            "rating": {".write": AND(other_user, "newData.isNumber()", "newData.val() >= 0", "newData.val() <= 5")},
            "totalRatings": {".write": AND(other_user, "newData.isNumber()",
                                           "newData.val() == (data.exists() ? data.val() : 0) + 1")},
            "timestamp": {".write": AND(other_user, "newData.isNumber()")},
        })

    return {
        ".read": AUTH,
        ".indexOn": ["isAvailable", "isActive", "work", "email"],
        "$uid": worker,
    }


def build_document_review_fields():
    """
    Campos de revisión de un documento. Los escribe el panel admin; el
    trabajador solo puede (re)subir un documento en 'pending'.
    """
    return {
        "status": {".validate": "newData.val() == data.val() || newData.val() == 'pending'"},
        "reviewedBy": {".validate": "newData.val() == data.val()"},
        "reviewedAt": {".validate": "newData.val() == data.val()"},
    }


def build(stage1=False):
    owner_only = AND(AUTH, "auth.uid == $uid")
    return {
        "rules": {
            ".read": False,
            ".write": False,
            "User": {
                "Clientes": {
                    "$uid": {
                        ".read": owner_only,
                        ".write": AND(owner_only, "newData.exists()"),
                    }
                },
                "Trabajadores": build_workers(stage1),
            },
            "active_workers": {
                ".read": AUTH,
                ".indexOn": ["g"],
                "$uid": {".write": owner_only},
            },
            "Tokens": {
                "$uid": {
                    # Etapa 1: la app actual lee el token del otro usuario para enviar
                    # FCM desde el teléfono. Final: FCM sale del backend (/api/notifications/)
                    ".read": AUTH if stage1 else owner_only,
                    ".write": owner_only,
                }
            },
            # WorkerDocuments/<uid>/<categoría>  (hojaDeVida, antecedentesJudiciales)
            # WorkerDocuments/<uid>/certificaciones/<subcategoría>/<docId>
            "WorkerDocuments": {
                "$uid": {
                    ".read": owner_only,
                    ".write": owner_only,
                    "$category": {
                        **build_document_review_fields(),
                        "$subcategory": {
                            "$documentId": build_document_review_fields(),
                        },
                    },
                }
            },
            "requests": build_requests(stage1),
        }
    }


def write(rules, file_name):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), file_name)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(rules, f, indent=2, ensure_ascii=False)
        f.write('\n')
    print(f"{file_name}: {len(json.dumps(rules))} caracteres")


if __name__ == '__main__':
    write(build(), 'database.rules.json')
    write(build(stage1=True), 'database.rules.stage1.json')
