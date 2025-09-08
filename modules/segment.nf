#!/usr/bin/env nextflow

nextflow.enable.dsl=2

// Read file lists (line-for-line pairing)
def fileList  = file(params.seg_in_files).text.readLines()
def maskList  = file(params.mask_files).text.readLines()
def boundList = file(params.bounds).text.readLines()

// Check that fileList and maskList lengths match
if (fileList.size() != maskList.size()) {
    exit 1, "ERROR: seg_in_files and mask_files must have the same number of lines"
}

// Pair in_files with mask_files, then expand over bounds
def pairingsList = fileList.indices.collectMany { i ->
    boundList.collect { bound ->
        tuple(fileList[i], maskList[i], bound)
    }
}

Channel
    .from(pairingsList)
    .set { pairings }


process Segment {

    label 'segment_job'

    input:
    tuple val(in_file), val(mask_file), val(bound)

    output:
    tuple path(prob_path), val(bound), emit: pairing

    script:
    """
    base_name=\$(basename "${in_file}")
    prob_path="${params.seg_out_dir}/\${base_name}.zarr"

    command="conda run -n ac python /allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Segment/cutout/submit.py \
      --weights_file ${params.weights_file} \
      --probability_output "\$prob_path" \
      --input_zarr ${in_file} \
      --bound_box ${bound} \
      --dsfactor ${params.dsfactor} \
      --mask_path ${mask_file}"

    \$command
    """
}

workflow {
    Segment(pairings)
}



