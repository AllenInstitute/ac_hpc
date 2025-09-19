#!/usr/bin/env nextflow

nextflow.enable.dsl=2

params.aws_key = 'None'
params.aws_sec_key = 'None'
params.out_endpoint = 'None'



// Channel to read file names from the input text file      
in_files = Channel.fromPath("${params.in_files}").flatMap { file ->
    file.text.readLines().collect { line -> 
        line.trim()  
    }
}

process createContainer {

    label 'deskew_job'

    input:
    val in_file

    script:
    """
    export TMPDIR="temp/"

    conda run -n ac python /ac_deploy/repos/axonal_connectomics/acpreprocessing/stitching_modules/convert_to_n5/tiff_to_ngff.py --tiffdir ${in_file} --output_n5 ${params.deskew_out_dir} --aws_key ${params.aws_key} --aws_sec_key ${params.aws_sec_key} --out_endpoint ${params.out_endpoint} 
    
    rm -rf \$TMPDIR
    """
}

workflow {
    createContainer(in_files)
}