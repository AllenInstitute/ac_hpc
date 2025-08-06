import os
import argschema
import pathlib
import docker
import torch
import skimage
import kimimaro
import cloudvolume
from cloudvolume import Skeleton
from scipy.spatial import KDTree
from joblib import Parallel, delayed, parallel_config, dump, load
import itertools
import scipy
import tarfile
import navis
import tarfile
from io import BytesIO
import concurrent.futures
import itertools
import numpy as np
from kimimaro.intake import merge
from matplotlib import pyplot as plt
import cc3d
import ast
from collections import defaultdict, deque
import networkx as nx
import uuid
import io


from ac_segmentation.utils.tensorstore import open_tensor, create_tensor, AWS_Parameters, create_kvstore
#from acanalysis.skeleton_reconstruction.util import read_navis_neurons_tar, kimi_to_navis, write_navis_skels_tar, merge_pairs, filter_skeletons, swc_split_branches, smooth_skeletons




def write_navis_skels_tar(tar_fn, skels, mode='w:gz', swcname=False):
    with tarfile.open(tar_fn, mode=mode) as t:
        for sk in skels:
            id = sk.id
            if swcname:
                id = sk.swcname
            if 'label' not in sk.nodes:
                sk.nodes.insert(1, 'label', list(np.zeros(len(sk.nodes))))
            sk = sk.nodes[['node_id', 'label','x','y','z','radius','parent_id']].values.tolist()
            for sub in sk:
                sub[0] = int(sub[0]) 
                sub[-1] = int(sub[-1]) 
            sk = '\n'.join(str(x)[1:-1] for x in sk).replace(",", "")
            bio = io.BytesIO(sk.encode())
            info = tarfile.TarInfo(name=f"{id}.swc")
            info.size = len(bio.getbuffer())
            t.addfile(tarinfo=info, fileobj=bio)


def label_binary_array(binary_arr, size_threshold=20):
    
    labeled_arr, num_features = cc3d.connected_components(binary_arr, connectivity=6, return_N=True)
    if num_features > 1:
        labeled_arr = skimage.morphology.remove_small_objects(
            labeled_arr, min_size=size_threshold, connectivity=3, out=labeled_arr)
        
    return labeled_arr, len(np.unique(labeled_arr))

def threshold_binarize_array(arr, threshold=0.2):
    return (arr >= threshold)

def skeletonize(out_arr, probability_threshold=0.2, label_size_threshold=50, scale=10, constant=10, 
                fill_holes=False, parallel=1, dust_threshold=10, max_paths=None):
    # binarize volume, label, and skeletonize
    binary_arr = threshold_binarize_array(out_arr, threshold=probability_threshold)
    labeled_arr, num_feat = label_binary_array(binary_arr, size_threshold=label_size_threshold)
    skels = kimimaro.skeletonize(
        labeled_arr,
        teasar_params={
            "scale": scale, 
            "const": constant, # influences the finger branches allowed
            "pdrf_scale": 10000,
            "pdrf_exponent": 1,
            "soma_acceptance_threshold": 3500, # physical units
            "soma_detection_threshold": 750, # physical units
            "soma_invalidation_const": 300, # physical units
            "soma_invalidation_scale": 2,
            "max_paths": max_paths, # default None
        },
        dust_threshold=dust_threshold, # skip connected components with fewer than this many voxels
        anisotropy=(1,1,1), # default True #influences the dimension scale
        fix_branching=True, # default True
        fix_borders=True, # default True
        fill_holes=fill_holes, # default False
        fix_avocados=False, # default False
        progress=False, # default False, show progress bar
        parallel=parallel, # <= 0 all cpu, 1 single process, 2+ multiprocess
        parallel_chunk_size=100, # how many skeletons to process before updating progress bar
    )

    return skels
    
    
###NEW EDIT
def kimi_to_navis(skels, tag=None):
    out_sk = navis.NeuronList(None)
    try:
        for sk in skels:
            sk = navis.TreeNeuron(sk.to_swc())
            if tag:
                sk.name = tag
            out_sk.append(sk)
    except:
        out_sk.append(navis.NeuronList(skels.to_swc()))

    return out_sk
    
    
###Edited
def create_chunked_dims(arr_shape, chunk_size, overlap=0):
    # Ensure chunk_size is appropriate for the arr_shape length
    if len(arr_shape) != len(chunk_size):
        raise ValueError("arr_shape and chunk_size must have the same number of dimensions")

    dx, dy, dz = arr_shape[-3:]
    xch, ych, zch = chunk_size

    starts_x = list(range(0, dx, xch))
    starts_y = list(range(0, dy, ych))
    starts_z = list(range(0, dz, zch))

    comb1, comb2 = [], []

    for sx, sy, sz in itertools.product(starts_x, starts_y, starts_z):
        ex, ey, ez = min(sx + xch, dx), min(sy + ych, dy), min(sz + zch, dz)

        # Expand by overlap pixels, within bounds
        sx, sy, sz = max(0, sx - overlap), max(0, sy - overlap), max(0, sz - overlap)
        ex, ey, ez = min(dx, ex + overlap), min(dy, ey + overlap), min(dz, ez + overlap)

        comb1.append((sx, sy, sz))
        comb2.append((ex, ey, ez))
        
    return comb1,comb2
    
    

def TS_skeletonize_volume(seg_arr, chunk_size=[1000, 1000, 1000], cutout=None, n_jobs=4, prob_thresh=0.2, label_size_threshold=20, overlap=4):
    def skel_chunk(start, end):
        arr = seg_arr[start[0]:end[0], start[1]:end[1], start[2]:end[2]]
        skels = skeletonize(
            np.array(arr),
            probability_threshold=prob_thresh,
            label_size_threshold=label_size_threshold
        )

        if skels:
            skels = [s for _, s in skels.items()]
            skels = Skeleton.simple_merge(skels).consolidate()
            skels.vertices += start  # shift back to global coords
            skels = kimi_to_navis(skels.components(), tag=str([start[0],end[0], start[1],end[1], start[2],end[2]]))
            return skels 

    if len(seg_arr.shape) == 5:
        seg_arr = seg_arr[0,0,:,:,:]
    start,end = create_chunked_dims(seg_arr.shape, chunk_size=chunk_size, overlap=overlap)

    if cutout:
        start_new,end_new = [],[]
        x1, x2, y1, y2, z1, z2 = cutout
        for i, (s, e) in enumerate(zip(start, end)):
            offset = np.array([x1,y1,z1])
            s, e = np.array(s[-3:])+offset, np.array(e[-3:])+offset
            if (s[0] <= x2 and s[1] <= y2 and s[2] <= z2):                         
                start_new.append(s)
                end_new.append(e)
        start,end = start_new,end_new

    with parallel_config(backend="loky", inner_max_num_threads=2):
        results = Parallel(n_jobs=n_jobs)(
            delayed(skel_chunk)(s, e) for s, e in zip(start, end)
        )

    results = navis.NeuronList([x for x in results if x != None])
    return results
    
 
###find overlapping neurons and then remove overlap

###NEW; SEE HOW THE EDITS CAN APPLY TO OTHER CUTOUT NODES FUNCTION, the id stuff
def keep_cutout_nodes(skels, bound_box=[0,0,0,0,0,0], min_nodes=3):
    out_sk = navis.NeuronList(None)
    remap = defaultdict(set)
    x1,x2,y1,y2,z1,z2 = bound_box
    for ind,sk in enumerate(skels):
        #find nodes within bounding box
        nodes = sk.nodes.copy()
        drop_nodes = list(nodes[~(nodes['x'].between(x1, x2) &nodes['y'].between(y1, y2) &nodes['z'].between(z1, z2))]['node_id'])
        og_id = sk.id
        
        #drop nodes from dataframe
        if len(drop_nodes)>0:
            nodes['parent_id'] = nodes['parent_id'].replace(drop_nodes,-1)
            nodes = nodes[~nodes['node_id'].isin(drop_nodes)].copy()
            if len(nodes) <= 1:
                continue
            nsk = navis.NeuronList(nodes.copy())  
            frag = navis.break_fragments(nsk)
            if len(frag) > 1 :
                for ind,fr in enumerate(frag):
                    if ind != 0:
                        if len(fr.nodes) > min_nodes:
                            fr.id = str(uuid.uuid4())
                            remap[str(og_id)].add(str(fr.id))
                            out_sk.append(fr)
                    else:
                        if len(fr.nodes) > min_nodes:
                            fr.id = og_id
                            out_sk.append(fr)
            else:
                frag[0].id = og_id
                out_sk.append(frag[0])
        else:
            out_sk.append(sk)

    return out_sk, remap


###NEW
def find_overlap(skels):
    coord_lookup = defaultdict(set)
    for sk in skels:
        nodes= sk.nodes[['x','y','z']].values
        for node in nodes:
            coord_lookup[str(node)].add(str(sk.id))

    matches = []
    for key,value in coord_lookup.items():
        if len(value) > 1:
            matches.append(tuple(value))

    return list(set(matches))


def find_remove_node_overlap(arr_shape, skels, overlap=4, n_jobs=8, block_size=[500,500,500]):

    #define chunks
    arr_shape = arr_shape[-3:]
    chunks = list(set(skels.name))
    chunks = [ast.literal_eval(x) for x in chunks]

    #define blocks, to minimize memory usage
    x_max, y_max, z_max = max(b[1] for b in chunks),  max(b[3] for b in chunks), max(b[5] for b in chunks)
    start,end = create_chunked_dims([x_max, y_max, z_max], chunk_size=block_size, overlap=0)
    blocks = [[x[0][0],x[1][0],x[0][1],x[1][1],x[0][2],x[1][2]] for x in zip(start,end)]
    block_groups = defaultdict(set)
    chunk_vol = {}

    #create chunk and block
    for ch in chunks:
        x1,x2,y1,y2,z1,z2 = ch
        start, end = np.array([x1,y1,z1]), np.array([x2,y2,z2])
        for bl in blocks:
            inside = all(
                max(v1, v2) >= bmin and min(v1, v2) <= bmax
                for v1, v2, bmin, bmax in zip(ch[::2], ch[1::2], bl[::2], bl[1::2])
            )
            if inside == True:
                block_groups[tuple(bl)].add(tuple(ch))
                pass
                
        for i in range(3):
            if start[i] == 0:
                start[i]=-1
                pass
            else:
                start[i] = start[i]+(overlap)
                
            if end[i] == arr_shape[i]:
                end[i] = arr_shape[i]+1
                pass
            else:
                end[i] = end[i]-(overlap)
                
        new_ch = [start[0],end[0],start[1],end[1],start[2],end[2]]
        chunk_vol[tuple(ch)] = [new_ch, navis.NeuronList([x for x in skels if x.name == str(ch)])]

    #create block groups for overlap detection
    block_vol = defaultdict()
    for block,blchunk in block_groups.items():
        skels = navis.NeuronList(None)
        for ch in blchunk:
            skels.append(chunk_vol[ch][1])
        block_vol[block] = skels

    #run parallel overlap detection
    with parallel_config(backend="loky", inner_max_num_threads=2):
        results = Parallel(n_jobs=n_jobs)(
            delayed(find_overlap)(value) for key,value in block_vol.items())
    match_pairs = [item for sublist in results for item in sublist]
    print("Completed overlap detection")

    #run parallel overlap removal
    with parallel_config(backend="loky", inner_max_num_threads=2):
        results = Parallel(n_jobs=n_jobs)(
            delayed(keep_cutout_nodes)(value[1], value[0]) for key,value in chunk_vol.items())
    print("Completed overlap removal")

    #remap matches
    neuro = navis.NeuronList(None)
    remap = {}
    for block in results:
        neuro.append(block[0])
        remap.update(block[1])

    for i in range(len(match_pairs)):
        new_match = match_pairs[i]
        for id in match_pairs[i]:
            if id in remap:
                new_match += tuple(remap[id])
        match_pairs[i] = new_match
        
    return match_pairs, neuro  
    
    
###merge pairs 

def merge_pairs_no_nodes(neuro_list, pair_data, min_nodes=5):
    merge_num = 0
    merge_list = navis.NeuronList(None)
    id_remap = {}        
    
    #create graph object with pairs
    G = nx.Graph()

    fpairs = []
    for pair in pair_data:
        for u, v in itertools.combinations(pair, 2):
            fpairs.append([str(u), str(v)])

    G.add_edges_from(fpairs)
    cc = list(nx.connected_components(G))
    neuro_ids = np.array([str(x) for x in neuro_list.id])
    remove = [] 

    for ind,com in enumerate(cc):
        group = []
        rem_ind = []
        for neu in com:
            s_ind = np.where(neuro_ids == str(neu))
            if len(s_ind[0])>0:
                rem_ind += [s_ind[0].astype(int)]
                if neuro_list[s_ind].n_nodes >= min_nodes:
                    group.append(neuro_list[s_ind])

        if len(group)>1:
            new_neu = navis.stitch_skeletons(group, method='LEAFS')
            merge_num += len(com)-1
            remove += rem_ind
            for neu in group:
                id_remap[neu.id[0]]=new_neu.id     
            #append to merge list
            merge_list.append(new_neu)
                
    print('finished the merging')
    #reset soma to none
    remove = set(int(i) for i in remove)
    unmerge_list = navis.NeuronList(None)
    for ind,x in enumerate(neuro_list):
        if ind not in remove:
            unmerge_list.append(x)
      
    #neuro_list = navis.NeuronList([x for ind,x in enumerate(neuro_list) if ind not in remove])
    
    for ind,neu in enumerate(unmerge_list):
        neu.soma = None
    
    id_remap = {key: value for key, value in id_remap.items() if key != value}
    print('Pairs Merged: ', merge_num)
    return unmerge_list, merge_list, id_remap



class CloudOptions(argschema.schemas.DefaultSchema):
    AWS_key = argschema.fields.String(required=False, default=None, allow_none=True)
    AWS_sec_key = argschema.fields.String(required=False, default=None, allow_none=True)
    region = argschema.fields.String(required=False, default='us-east-1')
    bound_box = argschema.fields.String(required=False, default=None, allow_none=True)
    endpoint = argschema.fields.String(required=False, default=None, allow_none=True)
    profile = argschema.fields.String(required=False, default=None, allow_none=True)
     

class SkeletonizeProbabilitiesParameters(argschema.ArgSchema):
    input_zarr = argschema.fields.String(required=True)
    skeleton_output = argschema.fields.String(required=True)
    probability_threshold = argschema.fields.Float(
        required=False, default=0.05)
    label_size_threshold = argschema.fields.Int(required=False, default=80)
    cloud_options = argschema.fields.Nested(
        CloudOptions, required=False)
    n_jobs = argschema.fields.Int(required=False, default=10)
    bound_box = argschema.fields.List(argschema.fields.Int(),required=False, default=None, allow_none=True)
    output_json = argschema.fields.OutputFile(required=False, allow_none=True)
    
class SkeletonizeProbabilitiesModule(argschema.ArgSchemaParser):
    default_schema = SkeletonizeProbabilitiesParameters

    def output(self, d):
        out_json = self.args.get("output_json")
        if out_json:
            pathlib.Path(out_json).parent.mkdir(parents=True, exist_ok=True)
            with open(out_json, "w") as f:
                json.dump(f, d)
                
    @property
    def cloud_options(self):
        try:
            return self.args["cloud_options"]  
        except:
            return {}

    def run(self):
        #if 'endpoint' in self.cloud_options:
            #cloud = self.cloud_options
            #if cloud['profile']:
                #AWS_param = AWS_Parameters(profile=cloud['profile'], region=cloud['region'], endpoint_url=cloud['endpoint'])                    
                            
            #if cloud['AWS_key']:
                #AWS_param = AWS_Parameters(region=cloud['region'], endpoint_url=cloud['endpoint'])
                #AWS_param.add_credentials(access_key_id=cloud['AWS_key'], secret_access_key=cloud['AWS_sec_key'])
                
            #kvstore = create_kvstore(fpath=self.args["input_zarr"], store='s3', AWS_param=AWS_param) 
            #array = open_tensor(kvstore=kvstore, driver='zarr3')
        
        
        array = open_tensor(fpath=self.args["input_zarr"], driver='zarr3')
        
        os.makedirs(self.args["skeleton_output"], exist_ok=True)
        skels_outpath = os.path.join(self.args["skeleton_output"], 'skeletons.swcs.tar.gz')
        
        if self.args["bound_box"]:
            skels_outpath = os.path.join(self.args["skeleton_output"], str(self.args["bound_box"]) + '.swcs.tar.gz')
            
        skels = TS_skeletonize_volume(array, chunk_size=[100,100,100], n_jobs=10, prob_thresh=.05, label_size_threshold=self.args["label_size_threshold"], overlap=4, cutout=self.args["bound_box"])
        print("Completed skeletonization")
        write_navis_skels_tar(skels_outpath,skels)
        #match_pairs, rem_skels = find_remove_node_overlap(array.shape,skels, overlap=4, block_size=[500,500,500])
        #print("Completed matching")
        #nonmerge,merge,remap = merge_pairs_no_nodes(rem_skels, match_pairs)
        #print("Completed merge")
        #out_skels = navis.NeuronList([nonmerge,merge])
        #write_navis_skels_tar(skels_outpath,out_skels)
            


if __name__ == "__main__":
    mod = SkeletonizeProbabilitiesModule()
    mod.run()


__all__ = [
    "SkeletonizeProbabilitiesModule",
    "SkeletonizeProbabilitiesParameters"
]

    
    
            