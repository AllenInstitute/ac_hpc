#!/usr/bin/env nextflow

nextflow.enable.dsl=2

params.out_dir = ''  
params.in_files = ''     
in_files = Channel.fromPath(params.in_files).splitText()

params.cloud_params = ''
def cloudParamsMap = params.cloud_params ? new groovy.json.JsonSlurper().parseText(params.cloud_params.replace("'", "\"")) : [:]

params.skel_params = ''
def SkelParamsMap = params.skel_params ? new groovy.json.JsonSlurper().parseText(params.skel_params.replace("'", "\"")) : [:]

process createContainer {
    input:
    val in_file

    script:
    """
    base_name=\$(basename ${in_file})
    export CLOUD_VOLUME_DIR=/home/
    command="conda run -n ac python "/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Skeletonize/submit.py" --input_zarr ${in_file} --skeleton_output ${params.out_dir}\${base_name}.swcs.tar.gz --probability_threshold ${SkelParamsMap.probability_threshold} --label_size_threshold ${SkelParamsMap.label_size_threshold} --cloud_options.region ${cloudParamsMap.region} --cloud_options.AWS_key ${cloudParamsMap.AWS_key} --cloud_options.AWS_sec_key ${cloudParamsMap.AWS_sec_key} --cloud_options.endpoint ${cloudParamsMap.endpoint} --n_jobs ${SkelParamsMap.n_jobs}"
    \$command \
    
    """
}

workflow {
    createContainer(in_files)
}

