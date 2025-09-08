#!/usr/bin/env nextflow

nextflow.enable.dsl=2

// Channel to read file names from the input text file
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

// Process
process createContainer {

    input:
    tuple val(in_file), val(bound)

    script:
    """
    command="conda run -n ac python /allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Downsample/submit.py --input_path ${in_file} --cutout ${bound}"

    \$command \
    
    """
}

workflow {
    createContainer(pairings)
}
