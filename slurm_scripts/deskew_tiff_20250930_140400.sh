#!/bin/bash
#SBATCH --job-name="deskew_tiff"
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --output=/home/connor.laughland/Documents/Repos/ac_hpc/slurm_logs/%x_%j_20250930.out
#SBATCH --error=/home/connor.laughland/Documents/Repos/ac_hpc/slurm_logs/%x_%j_20250930.err
#SBATCH --mem=25G
#SBATCH --time=60:00:00
#SBATCH --partition=emconnectome

export NXF_SINGULARITY_CACHEDIR="/home/connor.laughland/Documents/Repos/ac_hpc/singularity"

module load java/jdk-21.0.3

NXF_EX="/home/connor.laughland/Documents/Repos/ac_hpc/nextflow"
NXF_MAIN="/home/connor.laughland/Documents/Repos/ac_hpc/modules/deskew_tiff.nf"
config_file="/home/connor.laughland/Documents/Repos/ac_hpc/modules/main.config"

"$NXF_EX" run "$NXF_MAIN" --deskew_out_dir output/deskew_results --deskew_options {'deskew_method': 'None', 'deskew_stride': 1, 'deskew_transpose': 'False', 'deskew_flip': 'False'} --max_mip 5 --in_files inputs/in_files.txt --mask_files /home/connor.laughland/Documents/Repos/ac_hpc/inputs/mask_files.txt --bounds /home/connor.laughland/Documents/Repos/ac_hpc/inputs/bounds.txt --AWS_key 'None' --AWS_sec_key 'None' --region 'None' --endpoint 'None' -c "$config_file" -profile hpc
