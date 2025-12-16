from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import subprocess
import uuid
import os

app = FastAPI()

PYTHON = "python3"
PROGRAM = os.path.abspath("./main.py")  # adjust path if needed

class GenerateRequest(BaseModel):
    prompt: str

@app.post("/generate")
def generate(req: GenerateRequest):
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
