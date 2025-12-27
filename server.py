from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import subprocess
import uuid
import os
import requests
import sys
import signal

app = FastAPI()

# Use the *current* interpreter (your .venv python when uvicorn runs inside venv)
PYTHON = sys.executable
PROGRAM = os.path.abspath("./main.py")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "tinyllama:latest")  # safest default

class GenerateRequest(BaseModel):
    prompt: str

def run_generation(prompt: str):
    ensure_ollama_ready()
    print("Ollama found, starting program")
    job_id = uuid.uuid4().hex
    out_dir = f"/tmp/ar_jobs/{job_id}"
    os.makedirs(out_dir, exist_ok=True)
    zip_path = os.path.join(out_dir, "assets_bundle.zip")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"  # make prints flush

    try:
        proc = subprocess.run(
            [PYTHON, PROGRAM, "--prompt", prompt, "--zip-path", zip_path],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(PROGRAM),   # important for your relative data/ paths
            env=env,
            timeout=900,                    # 15 min; adjust if needed
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="PROGRAM_timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "PROGRAM_spawn_failed", "msg": str(e)})

    if proc.returncode != 0:
        sig = None
        if proc.returncode < 0:
            try:
                sig = signal.Signals(-proc.returncode).name
            except Exception:
                sig = f"SIG{-proc.returncode}"

        raise HTTPException(
            status_code=500,
            detail={
                "error": "PROGRAM_failed",
                "python": PYTHON,
                "program": PROGRAM,
                "returncode": proc.returncode,
                "signal": sig,
                "stdout_tail": (proc.stdout or "")[-4000:],
                "stderr_tail": (proc.stderr or "")[-8000:],
            },
        )

    if not os.path.exists(zip_path) or os.path.getsize(zip_path) == 0:
        raise HTTPException(status_code=404, detail="No assets were produced for this prompt.")

    return zip_path

@app.post("/generate")
def generate(req: GenerateRequest):
    zip_path = run_generation(req.prompt)
    return FileResponse(zip_path, media_type="application/zip", filename="assets_bundle.zip")

@app.get("/generate")
def generate_get(prompt: str):
    """
    Convenience GET endpoint so callers can supply ?prompt=... and receive the zip.
    """
    zip_path = run_generation(prompt)
    return FileResponse(zip_path, media_type="application/zip", filename="assets_bundle.zip")

def check_ollama(timeout: float = 1.0) -> dict:
    """
    Returns a dict describing Ollama status.
    Raises no exceptions (caller can decide how to respond).
    """
    status = {
        "ok": False,
        "ollama_url": OLLAMA_BASE_URL,
        "version": None,
        "model_installed": None,
        "error": None,
    }

    # 1) Server up?
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/version", timeout=timeout)
        r.raise_for_status()
        status["version"] = r.json().get("version")
    except Exception as e:
        status["error"] = f"ollama_unreachable: {e}"
        return status

    # 2) Model installed?
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=timeout)
        r.raise_for_status()
        models = r.json().get("models", [])
        names = {m.get("name") for m in models if isinstance(m, dict)}
        status["model_installed"] = (
    (OLLAMA_MODEL in names) or any(n.startswith(f"{OLLAMA_MODEL}:") for n in names)) # type: ignore
    except Exception as e:
        status["error"] = f"ollama_tags_failed: {e}"
        return status

    status["ok"] = bool(status["version"]) and bool(status["model_installed"])
    if not status["model_installed"]:
        status["error"] = f"model_not_installed: {OLLAMA_MODEL}"
    return status


@app.get("/health")
def health():
    s = check_ollama(timeout=1.0)
    code = 200 if s["ok"] else 503
    # FastAPI will still return 200 unless we raise; so raise on failure:
    if not s["ok"]:
        raise HTTPException(status_code=code, detail=s)
    return s


def ensure_ollama_ready():
    s = check_ollama(timeout=3.0)
    if not s["ok"]:
        print("Ollama failed to be found")
        # Fail fast with a clear message instead of hanging later
        raise HTTPException(status_code=503, detail=s)
