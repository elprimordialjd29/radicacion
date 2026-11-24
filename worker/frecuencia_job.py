"""Calcula en un proceso aparte (para no cargar la memoria del worker) los resultados por contrato que
faltan para la frecuencia de uso. Uso: python3 frecuencia_job.py tareas.json
tareas.json = {"motor": "asis|3280|todos", "cache": dir, "tareas": [{"archivos": [...], "out": ruta}, ...]}"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from motores import resultado_contrato  # noqa: E402

spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
t0 = time.time()
for t in spec["tareas"]:
    out = Path(t["out"])
    if out.exists():
        continue
    try:
        res = resultado_contrato(spec["motor"], t["archivos"], spec["cache"])
    except Exception as e:   # un RIPS ilegible no debe repetir el cálculo sin fin
        res = {"act": {}, "pg": {}, "n": {}, "s": {}, "pac": 0, "arch": len(t["archivos"]), "error": str(e)[:300]}
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(res, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    tmp.replace(out)
print(f"frecuencia: {len(spec['tareas'])} contratos ({spec['motor']}) en {time.time() - t0:.1f} s", flush=True)
