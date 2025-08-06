#!/bin/bash
#SBATCH --job-name=segment_single
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --output=my_job.out
#SBATCH --error=my_job.err
#SBATCH --mem=5G
#SBATCH --time=80:00:00
#SBATCH --partition=emconnectome

export NXF_SINGULARITY_CACHEDIR="/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Singularity_Images/"


weights_file='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Segment/single/best.ckpt'
config_file='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Segment/single/slurm.config'
#cloud_params="{'AWS_key':'' , 'AWS_sec_key':'', 'region':'us-east-1', 'bucket':'ac-test', 'endpoint':'http://aidc-ceph1-prd:8000'}"

in_files="/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Segment/single/in_files.txt"
cloud_params="{'AWS_key':'None' , 'AWS_sec_key':'None', 'region':'None', 'endpoint':'None'}"
out_dir='/allen/aind/stage/svc_axonal/hpc/segment/H17_PO11_S8_20250408/'
mask_dir='/allen/programs/celltypes/workgroups/em-connectomics/laughla/data/masks/H17_PO11_S8_20250408/'

NXF_EX="/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/nextflow"
NXF_MAIN="/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Segment/single/main.nf"

module load java/jdk-21.0.3

"$NXF_EX" run "$NXF_MAIN" --in_files "$in_files" --out_dir "$out_dir" --mask_dir "$mask_dir" --weights_file "$weights_file" --cloud_params "$cloud_params" -c "$config_file" -profile hpc