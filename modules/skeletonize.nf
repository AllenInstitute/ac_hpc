#!/usr/bin/env nextflow

nextflow.enable.dsl=2

// Read file lists (line-for-line pairing)
def fileList  = file(params.in_files).text.readLines()
def boundList = file(params.bounds).text.readLines()


// Pair in_files with mask_files, then expand over bounds
def pairingsList = fileList.indices.collectMany { i ->
    boundList.collect { bound ->
        tuple(fileList[i], bound)
    }
}

Channel
    .from(pairingsList)
    .set { pairings }


process Skeletonize {

    label 'skeletonize_job'	

    input:
    tuple val(in_file), val(bound)

    output:
    val("${params.skel_out_dir}/${last_two_dirs}.zarr"), emit: out_path

    script:
    """
    # Extract the last directory and filename of the input file path
    full_path="${in_file}"
    # Remove trailing slash if present
    full_path=\$(echo "\$full_path" | sed 's:/*\$::')
    # Get the last directory + filename
    last_dir=\$(echo "\$full_path" | awk -F'/' '{print \$(NF-1) "/" \$NF}')
    
    # Form output skeleton path
    skel_path="${params.skel_out_dir}/\${last_dir}"


    export CLOUD_VOLUME_DIR=/home/
    command="conda run -n ac python /ac_deploy/repos/ac_segmentation/src/ac_segmentation/postprocess/skeletonize_array.py \
      --input_zarr ${in_file} \
      --skeleton_output "\$skel_path" \
      --probability_threshold ${params.probability_threshold} \
      --label_size_threshold ${params.skeletonize.label_size_threshold} \
      --n_jobs ${params.skeletonize.n_jobs} \
      --cutout ${bound} \
      --AWS_key ${params.AWS_key} \
      --AWS_sec_key ${params.AWS_sec_key} \
      --region ${params.region} \
      --endpoint ${params.endpoint} \
      --profile ${params.profile}"

    \$command \
    
    """
}

workflow {
    Skeletonize(pairings)
}


