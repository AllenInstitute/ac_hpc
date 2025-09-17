from fastapi import FastAPI
from pydantic import BaseModel
import subprocess
import os
import tempfile

app = FastAPI()

# ====== CONFIGURE YOUR HPC INFO ======
HPC_USER = os.environ.get("HPC_USER", "svc_axonalconnectomi")
HPC_HOST = os.environ.get("HPC_HOST", "hpc.corp.alleninstitute.org")
HPC_PASSWORD = os.environ.get("HPC_PASSWORD", "yr6+Q$74")  # Use env variable!
HPC_PORT = int(os.environ.get("HPC_PORT", 22))
# =====================================

class JobRequest(BaseModel):
    script: str  # The SLURM job script content

@app.post("/jobs")
def submit_job(job: JobRequest):
    """
    Submits a SLURM job to the remote HPC by creating a job.sh script,
    copying it to the HPC node, and running sbatch.
    """
    try:
        # Create a temporary job.sh file locally
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".sh") as tmp_file:
            tmp_file.write(job.script)
            local_path = tmp_file.name

        remote_path = f"/tmp/{os.path.basename(local_path)}"  # Remote location

        # Copy the script to the remote HPC
        scp_cmd = [
            "sshpass",
            "-p", HPC_PASSWORD,
            "scp",
            "-o", "StrictHostKeyChecking=no",
            "-P", str(HPC_PORT),
            local_path,
            f"{HPC_USER}@{HPC_HOST}:{remote_path}"
        ]

        scp_result = subprocess.run(
            scp_cmd,
            capture_output=True,
            text=True
        )

        if scp_result.returncode != 0:
            return {"error": f"SCP failed: {scp_result.stderr.strip()}"}

        # Submit the job with sbatch on the remote HPC
        ssh_cmd = [
            "sshpass",
            "-p", HPC_PASSWORD,
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-p", str(HPC_PORT),
            f"{HPC_USER}@{HPC_HOST}",
            f"sbatch {remote_path}"
        ]

        ssh_result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True
        )

        if ssh_result.returncode != 0:
            return {"error": f"sbatch failed: {ssh_result.stderr.strip()}"}

        # Extract job_id from sbatch output
        try:
            job_id = ssh_result.stdout.strip().split()[-1]
        except IndexError:
            job_id = None

        return {"job_id": job_id, "message": ssh_result.stdout.strip()}

    finally:
        # Clean up the temporary file locally
        if os.path.exists(local_path):
            os.remove(local_path)
