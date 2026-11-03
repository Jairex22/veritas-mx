"""Server-side capability checks.

Every view that changes or exposes data calls :func:`has_cap` / :func:`require_cap`
and filters querysets by :func:`allowed_area_ids`. Hiding a button is never the
only control.
"""
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.http import JsonResponse

from .models import Role, RoleCapability

A, S, E, O, T = Role.ADMIN, Role.SUPERVISOR, Role.ENGINEER, Role.OPERATOR, Role.TECHNICIAN

# capability: (description, default roles)
CAPABILITIES = {
    "admin.users": ("Administrar usuarios, roles y áreas", {A}),
    "admin.settings": ("Configuración general, diagnóstico y respaldos", {A}),
    "admin.printers": ("Registrar y validar impresoras", {A}),
    "comms.publish": ("Publicar comunicados", {A, S}),
    "comms.comment": ("Comentar y registrar dudas/incidencias", {A, S, E, T, O}),
    "comms.resolve": ("Resolver incidencias", {A, S, E, T}),
    "production.view": ("Consultar plan de producción", {A, S, E, T, O}),
    "production.capture": ("Capturar avance en órdenes asignadas", {A, S, E, T, O}),
    "production.edit_plan": ("Modificar metas y prioridades del plan", {A, S}),
    "production.import": ("Importar archivos de datos", {A, S, E}),
    "production.revert": ("Revertir importaciones", {A, S}),
    "production.configure": ("Configurar datasets y reglas", {A, E}),
    "dashboard.view": ("Ver dashboards", {A, S, E, T, O}),
    "dashboard.build": ("Crear y compartir dashboards", {A, S, E}),
    "reports.generate": ("Generar reportes", {A, S, E}),
    "reports.schedule": ("Programar reportes", {A, S}),
    "sheets.edit": ("Crear y editar hojas de cálculo", {A, S, E}),
    "sheets.publish": ("Publicar cambios de hoja a un dataset", {A, S}),
    "documents.use": ("Usar el centro de documentos", {A, S, E, T, O}),
    "documents.transform": ("Transformar documentos", {A, S, E}),
    "labels.design": ("Diseñar plantillas de etiquetas", {A, S, E}),
    "labels.publish": ("Publicar versiones de plantillas", {A, S}),
    "labels.print": ("Imprimir etiquetas", {A, S, E, T, O}),
    "labels.reprint": ("Reimprimir etiquetas (con motivo)", {A, S}),
    "kaizen.create": ("Proponer mejoras Kaizen", {A, S, E, T, O}),
    "kaizen.evaluate": ("Evaluar, aprobar y cerrar Kaizen", {A, S}),
    "shift.use": ("Portal del turno: ver mi turno, pedir ayuda, paros, solicitudes", {A, S, E, T, O}),
    "shift.capture": ("Captura manual de producción (contingencia, queda provisional)", {A, S, E, T, O}),
    "shift.attend": ("Atender solicitudes de ayuda y materiales", {A, S, E, T}),
    "shift.plan": ("Asignar metas del turno", {A, S}),
    "shift.reconcile": ("Revisar conciliación de capturas manuales", {A, S}),
    "shift.close": ("Revisar y cerrar reportes de turno", {A, S}),
    "shift.quality": ("Dar disposición a observaciones de calidad", {A, S}),
    "shift.configure": ("Configurar piloto: líneas, estaciones, motivos, OData", {A}),
    "flx.status": ("FactoryLogix: ver estado de conexión y catálogo de entidades", {A, S, E, T}),
    "flx.query": ("FactoryLogix: consultas controladas (solo lectura) a entidades verificadas", {A, S, E}),
    "flx.admin": ("FactoryLogix: diagnóstico, actualización de esquema y sondeo controlado", {A}),
}


def _role(user):
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        return Role.ADMIN
    profile = getattr(user, "profile", None)
    return profile.role if profile else Role.OPERATOR


def capability_matrix():
    """Return {capability: set(roles)} merging DB overrides with defaults."""
    matrix = {cap: set(roles) for cap, (_d, roles) in CAPABILITIES.items()}
    for row in RoleCapability.objects.all():
        if row.capability not in matrix:
            continue
        if row.allowed:
            matrix[row.capability].add(row.role)
        else:
            matrix[row.capability].discard(row.role)
    return matrix


def has_cap(user, capability):
    role = _role(user)
    if role is None:
        return False
    if user.is_superuser:
        return True
    if capability not in CAPABILITIES:
        raise ValueError(f"Unknown capability {capability}")
    override = RoleCapability.objects.filter(role=role, capability=capability).first()
    if override is not None:
        return override.allowed
    return role in CAPABILITIES[capability][1]


def allowed_area_ids(user):
    """None means "all areas"; otherwise a set of Area ids."""
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return None
    profile = getattr(user, "profile", None)
    if profile is None:
        return set()
    if profile.all_areas or profile.role == Role.ADMIN:
        return None
    return set(profile.areas.values_list("id", flat=True))


def can_access_area(user, area_id):
    ids = allowed_area_ids(user)
    return ids is None or (area_id is not None and area_id in ids)


def filter_by_area(qs, user, field="area"):
    ids = allowed_area_ids(user)
    if ids is None:
        return qs
    return qs.filter(**{f"{field}__in": ids})


class CapabilityDenied(PermissionDenied):
    def __init__(self, capability):
        self.capability = capability
        desc = CAPABILITIES.get(capability, (capability,))[0]
        super().__init__(f"Su rol no tiene el permiso requerido: «{desc}». Solicítelo a un administrador.")


def require_cap(capability):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login

                return redirect_to_login(request.get_full_path())
            if not has_cap(request.user, capability):
                if request.headers.get("Accept", "").startswith("application/json") or request.path.startswith("/api/"):
                    desc = CAPABILITIES[capability][0]
                    return JsonResponse(
                        {"ok": False, "error": f"Permiso requerido: «{desc}». Solicítelo a un administrador."},
                        status=403,
                    )
                raise CapabilityDenied(capability)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def can_access_file(user, stored_file):
    """Authorization for a StoredFile download."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or stored_file.owner_id == user.id:
        return True
    from .models import StoredFile

    vis = stored_file.visibility
    if vis == StoredFile.Visibility.ALL:
        return True
    if vis == StoredFile.Visibility.AREA:
        return stored_file.area_id is not None and can_access_area(user, stored_file.area_id)
    # private: allow when the file is attached to something the user may see
    for checker in _FILE_ACCESS_HOOKS:
        if checker(user, stored_file):
            return True
    return False


_FILE_ACCESS_HOOKS = []


def register_file_access_hook(func):
    """Apps register functions(user, file) -> bool granting access through linked objects."""
    _FILE_ACCESS_HOOKS.append(func)
    return func
