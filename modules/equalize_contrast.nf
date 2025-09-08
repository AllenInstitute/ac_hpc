#!/usr/bin/env nextflow

nextflow.enable.dsl=2

// Parameters
params.out_dir = ''  
params.mask_dir = '' 
params.bounds = ''
params.in_files = ''

params.cloud_params = ''
def cloudParamsMap = params.cloud_params ? new groovy.json.JsonSlurper().parseText(params.cloud_params.replace("'", "\"")) : [:]

// Get file and bounds lists (blocking)
def fileList = file(params.in_files).text.readLines()
def boundList = file(params.bounds).text.readLines()

// Create all pairings (Cartesian product)
def pairingsList = fileList.collectMany { file ->
    boundList.collect { bound ->
        tuple(file, bound)
    }
}

// Emit pairings as a channel
Channel
    .from(pairingsList)
    .set { pairings }

// Process
process Contrast_Equalize {

    input:
    tuple val(in_file), val(bound)

    script:
    """
    base_name=\$(basename ${in_file})
    command="conda run -n ac python /allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Contrast/cutout/submit.py --input_path ${in_file}0/ --output_path ${params.out_dir}\${base_name}/0/ --region ${cloudParamsMap.region} --AWS_key ${cloudParamsMap.AWS_key} --AWS_sec_key ${cloudParamsMap.AWS_sec_key} --endpoint ${cloudParamsMap.endpoint} --cutout ${bound} --dsfactor 16 --mask_path ${params.mask_dir}\${base_name}/4/"

    \$command
    """
}

workflow {
    Contrast_Equalize(pairings)
}
