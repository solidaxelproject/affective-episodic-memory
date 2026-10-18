# Test di runtime/stato.py --imprimi-test: il self-check non tocca lo stato vero.
# Accanto a stato.py vive lo stato emotivo dell'agente (in produzione
# /data/workspace/memoria/stato-emotivo.json, letto da riflesso e tagging) e la sua
# eutimia.json: il self-check deve lavorare altrove. Gira senza GPU e senza rete.
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

QUI = Path(__file__).parent

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    shutil.copy(QUI / "runtime" / "stato.py", td / "stato.py")

    def autoverifica():
        r = subprocess.run([sys.executable, "stato.py", "--imprimi-test"], cwd=td,
                           capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0 and "self-check OK" in r.stdout, r.stdout + r.stderr

    # 1. lo stato vero e la sua eutimia ci sono: dopo il self-check sono intatti
    vero = {"ts": 1.0, "stato": {"joy": 1.25, "fear": -0.5}}
    eutimia = {"theta_ora": 0.1, "sigma": 0.0, "impronta": 0.25, "impronta_sem": 0.08,
               "tetto": 3.5, "baseline": {"joy": 0.2}}
    (td / "stato-emotivo.json").write_text(json.dumps(vero), encoding="utf-8")
    (td / "eutimia.json").write_text(json.dumps(eutimia), encoding="utf-8")
    autoverifica()
    assert (td / "stato-emotivo.json").exists(), "il self-check ha cancellato lo stato vero"
    assert json.loads((td / "stato-emotivo.json").read_text(encoding="utf-8")) == vero
    assert json.loads((td / "eutimia.json").read_text(encoding="utf-8")) == eutimia
    # 2. dove non c'e' niente, non lascia niente
    for f in ("stato-emotivo.json", "eutimia.json"):
        (td / f).unlink()
    autoverifica()
    rimasti = sorted(p.name for p in td.iterdir() if p.name not in ("stato.py", "__pycache__"))
    assert rimasti == [], f"il self-check ha lasciato {rimasti} accanto a stato.py"

print("test_stato: TUTTO VERDE")
