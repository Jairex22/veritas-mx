from apps.core.jobs import UserFacingError, job_handler


@job_handler("production.import_commit")
def run_import_commit(ctx):
    from .importer import commit
    from .models import ImportBatch

    batch = ImportBatch.objects.select_related("dataset", "source_file").get(pk=ctx.params["batch_id"])
    if batch.created_by_id and ctx.user and batch.created_by_id != ctx.user.id:
        raise UserFacingError("El lote pertenece a otro usuario.")
    ctx.progress(2, "Validando antes de aplicar")
    stats = commit(batch, ctx.user, ctx)
    return {"stats": stats, "batch_id": batch.pk, "url": f"/produccion/importaciones/{batch.pk}/"}


@job_handler("production.import_validate")
def run_import_validate(ctx):
    from .importer import validate
    from .models import ImportBatch

    batch = ImportBatch.objects.select_related("dataset", "source_file").get(pk=ctx.params["batch_id"])
    ctx.progress(10, "Leyendo y validando filas")
    result = validate(batch, ctx.user)
    return {"stats": result["stats"], "errors_total": result["errors_total"], "batch_id": batch.pk,
            "url": f"/produccion/importar/{batch.pk}/?paso=3"}


from apps.core.permissions import can_access_area, has_cap, register_file_access_hook  # noqa: E402


@register_file_access_hook
def import_files(user, stored_file):
    """Original import files and error reports: importers/reverters of the dataset area."""
    from .models import ImportBatch

    batches = ImportBatch.objects.filter(source_file=stored_file) | ImportBatch.objects.filter(error_file=stored_file)
    for b in batches.select_related("dataset"):
        if b.created_by_id == user.id:
            return True
        if (has_cap(user, "production.import") or has_cap(user, "production.revert")) and (
                b.dataset.area_id is None or can_access_area(user, b.dataset.area_id)):
            return True
    return False
