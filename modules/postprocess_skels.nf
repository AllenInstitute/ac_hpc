#!/usr/bin/env nextflow

nextflow.enable.dsl=2

in_files = Channel.fromPath(params.in_files).splitText()

process Postprocess_Skels {
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
    Postprocess_Skels(in_files)
}
