include { Segment } from './segment.nf'
include { Skeletonize } from './skeletonize.nf'


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



workflow { 
    Segment(pairings)
    Skeletonize(Segment.out.pairing)}