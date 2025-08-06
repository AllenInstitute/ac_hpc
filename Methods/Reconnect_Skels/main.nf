#!/usr/bin/env nextflow

nextflow.enable.dsl=2

params.out_dir = ''  
params.in_files = ''
params.sc='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Reconnect_Skels/model/scaler.joblib'
params.cl='/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Reconnect_Skels/model/LR_1.joblib'    
in_files = Channel.fromPath(params.in_files).splitText()

process createContainer {
    input:
    val in_file

    script:
    """
    base_name=\$(basename ${in_file})
    export CLOUD_VOLUME_DIR=/home/
    command="conda run -n ac python "/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Reconnect_Skels/submit.py" --skels ${in_file} --out_file ${params.out_dir}\${base_name} --cl ${params.cl} --sc ${params.sc}"
    \$command \
    
    """
}

workflow {
    createContainer(in_files)
}
