#!/bin/bash
#SBATCH --job-name=contrast_cutout
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --output=my_job.out
#SBATCH --error=my_job.err
#SBATCH --mem=20G
#SBATCH --time=60:00:00
#SBATCH --partition=emconnectome

export NXF_SINGULARITY_CACHEDIR="/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Singularity_Images/"

NXF_EX="/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/nextflow"
NXF_MAIN="/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Contrast/cutout/main.nf"
config_file='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Contrast/cutout/slurm.config'

in_files='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Contrast/cutout/in_files.txt'
bounds='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Contrast/cutout/bounds.txt'
out_dir='/allen/aind/stage/svc_axonal/hpc/contrast/exaSPIM_H17_PO11_S8_20250408_062325/'
mask_dir='/allen/programs/celltypes/workgroups/em-connectomics/laughla/data/masks/H17_PO11_S8_20250408/'
config_file='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Contrast/cutout/slurm.config'
cloud_params="{'AWS_key':'None', 'AWS_sec_key':'None', 'region':'None', 'endpoint':'None'}"

module load java/jdk-21.0.3

"$NXF_EX" run "$NXF_MAIN" --in_files "$in_files" --out_dir "$out_dir" --mask_dir "$mask_dir" --bounds "$bounds" --cloud_params "$cloud_params" -c "$config_file" -profile hpc