from apps.core.jobs import UserFacingError, job_handler

from .client import FlxError


@job_handler("flx.probe")
def job_probe(ctx):
    from .discovery import probe

    try:
        run = probe(ctx.params.get("names") or None, ctx.user, "web", progress=ctx.progress,
                    cancelled=lambda: _cancelled(ctx))
    except FlxError as e:
        raise UserFacingError(str(e))
    c = run.summary.get("counts", {})
    return {"summary": f"Sondeo terminado: {sum(c.values())} conjuntos · " + ", ".join(f"{k}: {v}" for k, v in sorted(c.items()))
            + (f" · {run.summary['stopped']}" if run.summary.get("stopped") else ""), "redirect": "/factorylogix/"}


def _cancelled(ctx):
    try:
        ctx.check_cancel()
        return False
    except Exception:
        return True
