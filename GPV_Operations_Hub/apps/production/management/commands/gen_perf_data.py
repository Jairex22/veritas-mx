import csv
import random
from datetime import date, timedelta
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Genera un CSV sintético reproducible de producción incremental (por defecto 100 000 filas) para pruebas de desempeño."

    def add_arguments(self, parser):
        parser.add_argument("--rows", type=int, default=100_000)
        parser.add_argument("--orders", type=int, default=2000)
        parser.add_argument("--seed", type=int, default=2026)
        parser.add_argument("--output", default="data/perf_produccion.csv")

    def handle(self, *args, **o):
        rnd = random.Random(o["seed"])
        out = Path(o["output"])
        out.parent.mkdir(parents=True, exist_ok=True)
        start = date(2026, 1, 1)
        lines = [f"L{i:02d}" for i in range(1, 21)]
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Fecha", "Turno", "Linea", "Area", "OT", "Estacion", "Buenas", "Rechazo", "Scrap", "Causa"])
            for i in range(o["rows"]):
                # key = date+shift+line+order+station: built from i so it is unique and deterministic
                order = i % o["orders"]
                d = start + timedelta(days=(i // (o["orders"] * 3)) % 300)
                shift = ("T1", "T2", "T3")[(i // o["orders"]) % 3]
                w.writerow([d.isoformat(), shift, lines[order % 20], "SMT", f"P{order:06d}", "FINAL", rnd.randint(5, 60), rnd.randint(0, 3),
                            rnd.randint(0, 1), "" if rnd.random() > 0.1 else "Soldadura fría"])
        self.stdout.write(f"{o['rows']} filas en {out}")
