#!/bin/bash
#SBATCH --job-name=copy_s3
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --output=my_job.out
#SBATCH --error=my_job.err
#SBATCH --mem=2G
#SBATCH --time=60:00:00
#SBATCH --partition=emconnectome

export NXF_SINGULARITY_CACHEDIR="/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Singularity_Images/"

NXF_EX="/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/nextflow"
NXF_MAIN="/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Copy_S3/main.nf"
config_file='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Copy_S3/slurm.config'

in_files='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Copy_S3/in_files.txt'
out_dir='s3://aibs-ac-public-sample-data/zarr/equalized/'
config_file='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Copy_S3/slurm.config'
cloud_params="{'AWS_key':'', 'AWS_sec_key':'', 'region':'us-west-2', 'endpoint':'None'}"


module load java/jdk-21.0.3

"$NXF_EX" run "$NXF_MAIN" --in_files "$in_files" --out_dir "$out_dir" --cloud_params "$cloud_params" -c "$config_file" -profile hpc

