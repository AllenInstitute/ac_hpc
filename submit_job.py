import requests
import argschema
from argschema import ArgSchema, ArgSchemaParser
from argschema.fields import List, Float, Nested
import sys
from marshmallow import validates_schema, ValidationError
import os
from pathlib import Path
import itertools
from datetime import datetime
import glob


REPO_DIR = Path(__file__).resolve().parent

job_template = """#!/bin/bash
#SBATCH --job-name="{method_name}"
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --output={slurm_out}/%x_%j_{date_str}.out
#SBATCH --error={slurm_out}/%x_%j_{date_str}.err
#SBATCH --mem=25G
#SBATCH --time=60:00:00
#SBATCH --partition=emconnectome

export NXF_SINGULARITY_CACHEDIR="{singularity_dir}"

module load java/jdk-21.0.3

NXF_EX="{nextflow_exec}"
NXF_MAIN="{nextflow_main}"
config_file="{config_file}"

"$NXF_EX" run "$NXF_MAIN" {method_parameters} -c "$config_file" -profile hpc
"""


def create_chunked_dims(arr_shape, chunk_size):
    if len(arr_shape) != len(chunk_size):
        raise ValueError("arr_shape and chunk_size must have the same number of dimensions")

    start_indices = []
    end_indices = []

    for dim_size, chunk in zip(arr_shape, chunk_size):
        start_indices.append(list(range(0, dim_size, chunk)))
        end_indices.append([min(dim_size, start + chunk) for start in start_indices[-1]])

    start = [list(item) for item in itertools.product(*start_indices)]
    end = [list(item) for item in itertools.product(*end_indices)]

    return start, end

def format_params_for_nextflow(params):
    args = []
    for k, v in params.items():
        if v is None or k == "log_level":
            continue
        args.append(f"--{k} {v}")
    return " ".join(args)


def build_job_script(
    method_name: str,
    nextflow_exec: str,
    nextflow_main: str,
    config_file: str,
    method_parameters: str,
    slurm_out: str
) -> str:
    Path(slurm_out).mkdir(parents=True, exist_ok=True)  # ensure folder exists
    
    # Get current date only
    date_str = datetime.now().strftime("%Y%m%d")
    
    return job_template.format(
        method_name=method_name,
        singularity_dir=str(REPO_DIR / "singularity"),
        nextflow_exec=nextflow_exec,
        nextflow_main=nextflow_main,
        config_file=config_file,
        method_parameters=method_parameters,
        slurm_out=slurm_out,
        date_str=date_str
    )


class NextflowFiles(argschema.ArgSchema):
    config_file = argschema.fields.String(
        required=True,
        dump_default=str(REPO_DIR / "modules" / "main.config")
    )
    process_file = argschema.fields.String(
        required=True,
        dump_default=str(REPO_DIR / "modules" / "main.nf")
    )


class CloudOptions(argschema.ArgSchema):
    AWS_key = argschema.fields.String(required=False, dump_default=None, allow_none=True)
    AWS_sec_key = argschema.fields.String(required=False, dump_default=None, allow_none=True)
    region = argschema.fields.String(required=False, dump_default='us-west-2')
    endpoint = argschema.fields.String(required=False, dump_default=None, allow_none=True)
    profile = argschema.fields.String(required=False, dump_default=None, allow_none=True)

class DeskewParameters(argschema.ArgSchema):
    deskew_in_files = argschema.fields.String(required=True, dump_default=str(REPO_DIR / "inputs" / "in_files.txt"))
    deskew_out_dir = argschema.fields.String(required=True, dump_default=None, allow_none=True)
    deskew_method = argschema.fields.String(required=False, dump_default='ps')
    deskew_stride = argschema.fields.Int(required=False, dump_default=2)
    deskew_transpose = argschema.fields.Boolean(required=False, dump_default=True)
    deskew_flip = argschema.fields.Boolean(required=False, dump_default=False)

class SegmentParameters(argschema.ArgSchema):
    seg_in_files = argschema.fields.String(required=True, dump_default=str(REPO_DIR / "inputs" /  "in_files.txt"))
    weights_file = argschema.fields.String(required=True, dump_default=None, allow_none=True)
    seg_out_dir = argschema.fields.String(required=True, dump_default=None, allow_none=True)
    filter_max_intensity = argschema.fields.Int(required=False, dump_default=30000, allow_none=True)
    rescale_perc = argschema.fields.String(allow_none=True, dump_default='[96,97]')
    bounds = argschema.fields.String(required=True, dump_default=str(REPO_DIR / "inputs" /  "bounds.txt"))
    dsfactor = argschema.fields.Int(required=False, dump_default=16, allow_none=True)
    mask_files = argschema.fields.String(required=False, allow_none=True, dump_default=str(REPO_DIR / "inputs" /  "mask_files.txt"))

class SkeletonizeParameters(argschema.ArgSchema):
    skel_in_files = argschema.fields.String(required=True, dump_default=str(REPO_DIR / "inputs" /  "in_files.txt"))
    skel_out_dir = argschema.fields.String(required=True, dump_default=None, allow_none=True)
    probability_threshold = argschema.fields.Float(required=False, dump_default=0.05)
    label_size_threshold = argschema.fields.Int(required=False, dump_default=80)
    n_jobs = argschema.fields.Int(required=False, dump_default=10)
    bounds = argschema.fields.String(required=True, dump_default=str(REPO_DIR / "inputs" /  "bounds.txt"))
    output_json = argschema.fields.OutputFile(required=False, allow_none=True)
    
    
class PostprocessParameters(argschema.ArgSchema):
    postprocess_in_dir = argschema.fields.String(required=True, dump_default=None, allow_none=True)
    postprocess_out_dir = argschema.fields.String(required=True, dump_default=None, allow_none=True)
    output_json = argschema.fields.OutputFile(required=False, allow_none=True)


class SlurmOptions(argschema.ArgSchema):
    out_dir = argschema.fields.String(
        required=False,
        dump_default=str(REPO_DIR / "slurm_logs"))

class Methods(ArgSchema):
    method = argschema.fields.String(required=True)
    chunking_shape = argschema.fields.Raw(required=False, dump_default=None, allow_none=True)
    segment = Nested(SegmentParameters, required=False)
    skeletonize = Nested(SkeletonizeParameters, required=False)
    postprocess = Nested(PostprocessParameters, required=False)
    cloud_params = Nested(CloudOptions, required=False)
    nf_files = Nested(
        NextflowFiles,
        required=True,
        dump_default={
            'config_file': str(REPO_DIR / "modules" / "main.config"),
            'process_file': str(REPO_DIR / "modules" / "main.nf")
        }
    )
    slurm = Nested(SlurmOptions, required=False)


class SubmitJobModule:
    def __init__(self, args):
        self.args = args

    def run(self):
        hpc_api_url = 'http://hpc.corp.alleninstitute.org:8002/jobs'

        method = self.args['method']
        if method == 'seg&skel':
            seg_param = self.args['segment']
            skel_param = self.args['skeletonize']
            method_parameters = seg_param | skel_param
            
        else:
            method_parameters = self.args[method]
            
        nf_params = self.args['nf_files']
        all_parameters = format_params_for_nextflow(method_parameters)

        slurm_out = self.args.get("slurm", {}).get("out_dir") or str(REPO_DIR / "slurm_logs")

        job_script = build_job_script(
            method_name=method,
            nextflow_exec=str(REPO_DIR / "nextflow"),
            nextflow_main=str(Path(self.args['nf_files']['process_file']).with_name(f"{method}.nf")),
            config_file=self.args['nf_files']['config_file'],
            method_parameters=all_parameters,
            slurm_out=slurm_out
        )

        payload = {'script': job_script}
        response = requests.post(hpc_api_url, json=payload)
        
        print(job_script)

        if response.ok:
            print("Job submitted successfully!")
            print("Response:", response.json())
        else:
            print(f"Failed to submit job: {response.status_code} {response.text}")


required_params_map = {
    "segment": ["weights_file", "seg_out_dir"],
    "skeletonize": ["skel_out_dir"],
    "postprocess": ["postprocess_in_dir", "postprocess_out_dir"]
}


def check_required_params(method, args, required_params_map):
    method_args = args.get(method) or {}
    required_fields = required_params_map[method]
    missing = [f for f in required_fields if not method_args.get(f)]
    if missing:
        raise ValueError(f"Missing required parameters for '{method}' method: {missing}")


if __name__ == "__main__":
    parser = ArgSchemaParser(schema_type=Methods)
    args = parser.args
    method = args.get("method")

    if method == "segment":
        check_required_params('segment', args, required_params_map)
    elif method == "skeletonize":
        check_required_params('skeletonize', args, required_params_map)
    elif method == "seg&skel":
        check_required_params('segment', args, required_params_map)
        check_required_params('skeletonize', args, required_params_map)
    elif method == "postprocess":
        check_required_params('postprocess', args, required_params_map)  
        post_dir = args['postprocess']['postprocess_in_dir']
    
        # Find all .swc files in the input directory
        swc_files = sorted(glob.glob(os.path.join(post_dir, "*.swc")))
        if not swc_files:
            raise ValueError(f"No .swc files found in directory: {post_dir}")
    
        # Write them to in_files.txt
        in_files_path = Path(REPO_DIR / "inputs" /  "in_files.txt")
        in_files_path.write_text("\n".join(swc_files))
        print(f"Wrote {len(swc_files)} .swc files to {in_files_path}")     
    else:
        raise ValueError("Choose one of: segment, skeletonize, seg&skel")

    print(f"All required parameters for method '{method}' are present.")

    in_files = [l.strip() for l in Path(str(REPO_DIR / "inputs" /  "in_files.txt")).read_text().splitlines() if l.strip()]
    mask_file_path = Path(str(REPO_DIR / "inputs" /  "mask_files.txt"))
    mask_files = []

    if args.get("chunking_shape"):
        bounds = []
        x, y, z = [int(x.strip("'")) for x in args.get("chunking_shape").split(" ")]
        inter = list(range(0, x, int(x / 40)))
        for xi in range(len(inter) - 1):
            bounds.append('{0},{1},0,{2},0,{3}'.format(inter[xi], inter[xi + 1], y, z))

        with open(str(REPO_DIR / "inputs" /  "bounds.txt"), "w") as f:
            for i, b in enumerate(bounds):
                if i < len(bounds) - 1:
                    f.write(f'"{b}"\n')
                else:
                    f.write(f'"{b}"')

        print(f"bounds.txt cleared and written with {len(bounds)} entries")

    else:
        with open(str(REPO_DIR / "inputs" /  "bounds.txt"), "w") as f:
            f.write('None')

    if mask_file_path.exists():
        raw_lines = [l.strip() for l in mask_file_path.read_text().splitlines() if l.strip()]
        if raw_lines and raw_lines[0] == "None":
            raw_lines = []
        mask_files = raw_lines

    if not mask_files:
        mask_files = ["None"] * len(in_files)
        mask_file_path.write_text("\n".join(mask_files))

    mod = SubmitJobModule(args)
    mod.run()


__all__ = [
    "SubmitJobModule",
    "Methods"
]
