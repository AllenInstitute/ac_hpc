####run from hpc user with "nohup uvicorn app:app --host 0.0.0.0 --port PORT_NUMBER > slurm_api.log 2>&1 &"


from fastapi import FastAPI
from pydantic import BaseModel
import subprocess

app = FastAPI()

class JobRequest(BaseModel):
    script: str  # The SLURM job script content

@app.post("/jobs")
def submit_job(job: JobRequest):
    # Save the script to a temp file
    with open("job.sh", "w") as f:
        f.write(job.script)
    # Submit the job via sbatch
    result = subprocess.run(["sbatch", "job.sh"], capture_output=True, text=True)
    if result.returncode != 0:
        return {"error": result.stderr}
    # Example output: "Submitted batch job 12345"
    job_id = result.stdout.strip().split()[-1]
    return {"job_id": job_id, "message": result.stdout.strip()}
