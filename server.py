from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import subprocess
import uuid
import os
import requests

app = FastAPI()

PYTHON = "python3"
PROGRAM = os.path.abspath("./main.py")  # adjust path if needed
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "tinyllama")

class GenerateRequest(BaseModel):
    prompt: str

@app.post("/generate")
def generate(req: GenerateRequest):
    ensure_ollama_ready()
    job_id = uuid.uuid4().hex
    out_dir = f"/tmp/ar_jobs/{job_id}"
    os.makedirs(out_dir, exist_ok=True)

    zip_path = os.path.join(out_dir, "assets_bundle.zip")

    # run PROGRAM synchronously
    proc = subprocess.run(
        [PYTHON, PROGRAM, "--prompt", req.prompt, "--zip-path", zip_path],
        capture_output=True,
        text=True,
    )

    if proc.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "PROGRAM_failed",
                "stdout_tail": proc.stdout[-2000:],
                "stderr_tail": proc.stderr[-2000:],
            },
        )

    if not os.path.exists(zip_path) or os.path.getsize(zip_path) == 0:
        raise HTTPException(status_code=404, detail="No assets were produced for this prompt.")

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename="assets_bundle.zip",
    )


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
        status["model_installed"] = (OLLAMA_MODEL in names)
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
    s = check_ollama(timeout=1.0)
    if not s["ok"]:
        # Fail fast with a clear message instead of hanging later
        raise HTTPException(status_code=503, detail=s)
