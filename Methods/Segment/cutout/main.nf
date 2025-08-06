#!/usr/bin/env nextflow

nextflow.enable.dsl=2

params.out_dir = '' 
params.weights_file = ''
params.mask_dir = '' 
params.in_files = ''
params.bounds = '' 

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

params.cloud_params = ''
def cloudParamsMap = params.cloud_params ? new groovy.json.JsonSlurper().parseText(params.cloud_params.replace("'", "\"")) : [:]

process createContainer {

    input:
    tuple val(in_file), val(bound)

    script:
    """
    base_name=\$(basename "${in_file}")
    command="conda run -n ac python /allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Segment/cutout/submit.py --weights_file ${params.weights_file} --probability_output ${params.out_dir}\${base_name}.zarr --input_zarr ${in_file} --cloud_options.region ${cloudParamsMap.region} --cloud_options.AWS_key ${cloudParamsMap.AWS_key} --cloud_options.AWS_sec_key ${cloudParamsMap.AWS_sec_key} --cloud_options.endpoint ${cloudParamsMap.endpoint} --bound_box ${bound} --dsfactor 16 --mask_path ${params.mask_dir}\${base_name}/4/"

    \$command
    """
}

workflow {
    createContainer(pairings)
}


