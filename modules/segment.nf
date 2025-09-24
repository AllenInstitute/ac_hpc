#!/usr/bin/env nextflow

nextflow.enable.dsl=2

// Read file lists (line-for-line pairing)
def fileList  = file(params.in_files).text.readLines()
def maskList  = file(params.mask_files).text.readLines()
def boundList = file(params.bounds).text.readLines()
params.mip = 0

params.seg_out_dir = params.seg_out_dir.replaceAll(/\/$/, '')


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
    tuple val("${params.seg_out_dir}/${file(in_file).baseName}.zarr/${params.mip}"), val(bound), emit: pairs

    script:
    """
    prob_path="${params.seg_out_dir}/${file(in_file).baseName}.zarr/${params.mip}"
    in_file=\$(echo "${in_file}" | sed 's:/*\$::')

    command="conda run -n ac python /ac_deploy/repos/ac_segmentation/src/ac_segmentation/gunpowder/segment_array.py \
      --weights_file ${params.weights_file} \
      --probability_output "\$prob_path" \
      --input_zarr "\$in_file/${params.mip}" \
      --cutout ${bound} \
      --dsfactor ${params.dsfactor} \
      --mask_path ${mask_file} \
      --AWS_key ${params.AWS_key} \
      --AWS_sec_key ${params.AWS_sec_key} \
      --region ${params.region} \
      --endpoint ${params.endpoint} \
      --profile ${params.profile}"

    \$command
    """
}

workflow {
    Segment(pairings)
}



