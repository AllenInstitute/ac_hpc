#!/usr/bin/env nextflow

nextflow.enable.dsl=2

params.out_dir = '' 
params.in_files = ''     
in_files = Channel.fromPath(params.in_files).splitText()
  
params.cloud_params = ''
def cloudParamsMap = params.cloud_params ? new groovy.json.JsonSlurper().parseText(params.cloud_params.replace("'", "\"")) : [:]


process createContainer {

    input:
    val in_file

    script:
    """
    base_name=\$(basename ${in_file})
    command="conda run -n ac python /allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Copy_S3/submit.py --input_path ${in_file} --output_path ${params.out_dir}\${base_name}/ --AWS_key ${cloudParamsMap.AWS_key} --AWS_sec_key ${cloudParamsMap.AWS_sec_key}"

    \$command \
    
    """
}

workflow {
    createContainer(in_files)
}