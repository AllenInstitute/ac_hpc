#!/usr/bin/env nextflow

nextflow.enable.dsl=2


// Read file lists (line-for-line pairing)
def fileList  = file(params.in_files).text.readLines()
def maskList  = file(params.mask_files).text.readLines()
def boundList = file(params.bounds).text.readLines()


// Pair in_files with mask_files, then expand over bounds
def pairingsList = fileList.indices.collectMany { i ->
    boundList.collect { bound ->
        tuple(fileList[i], maskList[i], bound)
    }
}

Channel
    .from(pairingsList)
    .set { pairings }

// Process
process Contrast_Equalize {

    label 'equalize_job'

    input:
    tuple path(in_file), val(mask_file), val(bound)

    script:
    """
    base_name=\$(basename ${in_file})
    command="conda run -n ac python /allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Contrast/cutout/submit.py --input_path ${in_file} --output_path ${params.equal_out_dir}/\${base_name} --cutout ${bound} --dsfactor ${params.dsfactor} --mask_path ${mask_file}"

    \$command
    """
}

workflow {
    Contrast_Equalize(pairings)
}
