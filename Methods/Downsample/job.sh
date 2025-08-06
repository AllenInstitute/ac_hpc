#!/bin/bash
#SBATCH --job-name=downsample
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --output=my_job.out
#SBATCH --error=my_job.err
#SBATCH --mem=10G
#SBATCH --time=60:00:00
#SBATCH --partition=emconnectome

export NXF_SINGULARITY_CACHEDIR="/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Singularity_Images/"

NXF_EX="/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/nextflow"
NXF_MAIN="/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Downsample/main.nf"

in_files='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Downsample/in_files.txt'
bounds='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Downsample/bounds.txt'
config_file='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Downsample/slurm.config'

module load java/jdk-21.0.3

"$NXF_EX" run "$NXF_MAIN" --in_files "$in_files" --bounds "$bounds"  -c "$config_file" -profile hpc

