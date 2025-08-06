#!/bin/bash
#SBATCH --job-name=reconnect_skels
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --output=my_job.out
#SBATCH --error=my_job.err
#SBATCH --mem=2G
#SBATCH --time=60:00:00
#SBATCH --partition=emconnectome


export NXF_SINGULARITY_CACHEDIR="/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Reconnect_Skels/input/"

in_files='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Reconnect_Skels/in_files.txt' 
out_dir='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Reconnect_Skels/'  
config_file='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Reconnect_Skels/slurm.config'
sc='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Reconnect_Skels/model/scaler.joblib'
cl='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Reconnect_Skels/model/LR_1.joblib'

NXF_EX="/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/nextflow"
NXF_MAIN="/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Reconnect_Skels/main.nf"

module load java/jdk-21.0.3

"$NXF_EX" run "$NXF_MAIN" --in_files "$in_files" --out_dir "$out_dir" -c "$config_file"