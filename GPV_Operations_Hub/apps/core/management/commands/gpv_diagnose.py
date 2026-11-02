from django.core.management.base import BaseCommand

from apps.core.diagnostics import run_all


class Command(BaseCommand):
    help = "Diagnóstico: base de datos, migraciones, carpetas, convertidores, trabajos, planificador e impresoras."

    def handle(self, *args, **opts):
        errors = 0
        for section in run_all():
            self.stdout.write(f"\n== {section['title']} ==")
            for i in section["items"]:
                mark = {"ok": "[OK]  ", "warn": "[AVISO]", "error": "[ERROR]", "info": "[INFO]"}.get(i["status"], i["status"])
                self.stdout.write(f"{mark} {i['name']}: {i['detail']}")
                if i.get("fix"):
                    self.stdout.write(f"        → {i['fix']}")
                errors += i["status"] == "error"
        self.stdout.write(f"\nResultado: {'sin errores' if not errors else str(errors) + ' error(es)'}")
        if errors:
            raise SystemExit(1)
