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


process Segment {

    label 'segment_job'

    input:
    tuple path(in_file), val(mask_file), val(bound)

    output:
    tuple val("${params.seg_out_dir}/${in_file.baseName}.zarr"), val(bound), emit: pairs

    script:
    """
    prob_path="${params.seg_out_dir}/${in_file.baseName}.zarr"

    command="conda run -n ac python /ac_deploy/repos/ac_segmentation/src/ac_segmentation/gunpowder/segment_array.py \
      --weights_file ${params.weights_file} \
      --probability_output "\$prob_path" \
      --input_zarr ${in_file} \
      --cutout ${bound} \
      --dsfactor ${params.dsfactor} \
      --mask_path ${mask_file}"

    \$command
    """
}

workflow {
    Segment(pairings)
}



