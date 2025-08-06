#!/bin/bash
#SBATCH --job-name=skeletonize
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --output=my_job.out
#SBATCH --error=my_job.err
#SBATCH --mem=12G
#SBATCH --time=60:00:00
#SBATCH --partition=emconnectome


export NXF_SINGULARITY_CACHEDIR="/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Singularity_Images/"

in_files='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Skeletonize/cutout/in_files.txt'
bounds='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Skeletonize/cutout/bounds.txt'
out_dir='/allen/aind/stage/svc_axonal/hpc/skeletons/H17_PO11_S8_20250408/'
config_file='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Skeletonize/cutout/slurm.config'
skel_params="{'probability_threshold':'0.05', 'label_size_threshold':'100', 'n_jobs':'10'}"
cloud_params="{'AWS_key':'' , 'AWS_sec_key':'', 'region':'us-east-1', 'endpoint':'http://aidc-ceph1-prd:8000'}"

NXF_EX="/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/nextflow"
NXF_MAIN="/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Skeletonize/cutout/main.nf"

module load java/jdk-21.0.3

"$NXF_EX" run "$NXF_MAIN" --in_files "$in_files" --out_dir "$out_dir"  --skel_params "$skel_params" --bounds "$bounds" --cloud_params "$cloud_params" -c "$config_file" -profile hpc
