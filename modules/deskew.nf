#!/usr/bin/env nextflow

nextflow.enable.dsl=2

// Channel to read file names from the input text file
params.in_files = ''        
in_files = Channel.fromPath("${params.deskew_in_files}").flatMap { file ->
    file.text.readLines().collect { line -> 
        line.trim()  
    }
}


// Parse deskew and cloud parameters
def deskew_param = params.deskew_options ? new groovy.json.JsonSlurper().parseText(params.deskew_options.replace("'", "\"")) : [:]

process Deskew {


    input:
    val in_file

    script:
    """	
    base_name=\$(basename ${in_file})
    command="conda run -n ac python /allen/programs/celltypes/workgroups/em-connectomics/laughla/Slurm/Deskew/zarr3_to_nfss/submit.py --input_file ${in_file} --output_file ${params.deskew_out_dir}\${base_name} --group_names \${base_name} --max_mip ${params.max_mip} --output_format zarr --concurrency 5 --deskew_options.deskew_method ${deskew_param.deskew_method} --deskew_options.deskew_stride ${deskew_param.deskew_stride} --deskew_options.deskew_transpose ${deskew_param.deskew_transpose} --deskew_options.deskew_flip ${deskew_param.deskew_flip} --compression blosc"

    \$command \


    """
}

workflow {
    Deskew(in_files)
}
