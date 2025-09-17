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
    val("${params.skel_out_dir}/\${base_name}.zarr"), emit: out_path

    script:
    """
    base_name=\$(basename "${in_file}")
    prob_path="${params.skel_out_dir}/\${base_name}.zarr"


    export CLOUD_VOLUME_DIR=/home/
    command="conda run -n ac python "/allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Skeletonize/cutout/submit.py" --input_zarr ${in_file} --skeleton_output "\$prob_path" --probability_threshold ${params.probability_threshold} --label_size_threshold ${params.skeletonize.label_size_threshold} --n_jobs ${params.skeletonize.n_jobs} --bound_box ${bound}"
    \$command \
    
    """
}

workflow {
    Skeletonize(pairings)
}


