###changed it so nonoverlap is written first without blending, to remove the perimeter artifact


import argschema

import configparser
from typing import Optional
import numpy as np
import tensorstore as ts
import os
import json
import boto3
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from typing_extensions import Self
import torch


def split_s3_path(s3_path):
    if 'https' in s3_path:
        path_parts=s3_path.replace("https://","").split("/")
        bucket=path_parts.pop(0).split(".s3")[0]
        key="/".join(path_parts)
    else:
        path_parts=s3_path.replace("s3://","").split("/")
        bucket=path_parts.pop(0)
        key="/".join(path_parts)
    return bucket, key

class AWS_Parameters:
    entries: dict[int, tuple[str, str]]
    temp_dir: TemporaryDirectory[str]
    credentials_file_path: Path
    @classmethod
    @lru_cache
    def singleton(cls) -> "Self":
        return cls()
        
    def __init__(self, profile=None, region=None, endpoint_url=None):
        self.entries = {}
        self.temp_dir = TemporaryDirectory()
        self.credentials_file_path = Path(self.temp_dir.name) / "aws_credentials"
        self.credentials_file_path.touch()
        #create session
        session = boto3.Session(profile_name=profile, region_name=region)
        if endpoint_url:
            self.endpoint_url=endpoint_url
        self.profile=session.profile_name
        self.region=session.region_name
    def _dump_credentials(self) -> None:
        self.credentials_file_path.write_text(
            "\n".join(
                [
                    f"[{self.profile}]\naws_access_key_id = {access_key_id}\naws_secret_access_key = {secret_access_key}\n"
                    for key_hash, (
                        access_key_id,
                        secret_access_key,
                    ) in self.entries.items()
                ]
            )
        )
    def add_credentials(self, access_key_id: str, secret_access_key: str) -> dict[str, str]:
        key_tuple = (access_key_id, secret_access_key)
        key_hash = hash(key_tuple)
        self.entries[key_hash] = key_tuple
        self._dump_credentials()
        self.credential_file = {
            "profile": f"profile-{key_hash}",
            "filename": str(self.credentials_file_path),
            "metadata_endpoint": "",
        }


def create_kvstore(fpath, store, AWS_param=None):
    """Creates the kvstore configuration based on the input parameters.

    Args:
        fpath (str): Path to the tensorstore file or S3 URL.
        store (str): Type of store ('file' or 's3').
        AWS_param (Optional[dict]): AWS credentials and parameters (only used for S3).

    Returns:
        dict: The kvstore configuration.
    """
    kvstore = {"driver": store, "path": fpath}
    
    if store == 's3':
        # Parse the S3 URL into bucket and path
        bucket, path = split_s3_path(fpath)
        kvstore = {"driver": "s3", "bucket": bucket, "path": path}
        
        if AWS_param:
            kvstore.update({"aws_region": AWS_param.region})
            if hasattr(AWS_param, "endpoint_url"):
                kvstore.update({"endpoint": AWS_param.endpoint_url})
            
            # Handle credentials
            cred = {"aws_credentials": {"profile": AWS_param.profile}}
            if hasattr(AWS_param, "credential_file"):
                cred = {"aws_credentials": {
                    "profile": AWS_param.profile,
                    "filename": AWS_param.credential_file['filename']
                }}
            kvstore.update(cred)
    
    return kvstore
    
    
def open_tensor(fpath=None, kvstore=None, driver='zarr', bytes_limit=100_000_000):
    """Open a tensorstore object.

    Args:
        fpath (str): Path to the tensorstore file or S3 URL.
        driver (str): Type of file (e.g., 'zarr', 'n5', 'precomputed').
        kvstore (dict, optional): Pre-constructed kvstore configuration.
        bytes_limit (int): Memory limit for in-memory cache in bytes (default 100MB).

    Returns:
        tensorstore.Dataset: The opened tensorstore dataset.
    """
    # If kvstore is not provided, create it from fpath
    if kvstore is None:
        kvstore = create_kvstore(fpath, store='file', AWS_param=None)

    # Check if zarr v3
    if 'zarr' in driver:
        # Load the tensorstore array with cache configuration
        try:
            dataset_future = ts.open({
                'driver': 'zarr',
                'kvstore': kvstore,
                'context': {
                    'cache_pool': {
                        'total_bytes_limit': bytes_limit
                    }
                },
                'recheck_cached_data': 'open',
            })
            return dataset_future.result()
    
        except:
            dataset_future = ts.open({
                'driver': 'zarr3',
                'kvstore': kvstore,
                'context': {
                    'cache_pool': {
                        'total_bytes_limit': bytes_limit
                    }
                },
                'recheck_cached_data': 'open',
            })
            return dataset_future.result()
            
    else:
         dataset_future = ts.open({
                'driver': driver,
                'kvstore': kvstore,
                'context': {
                    'cache_pool': {
                        'total_bytes_limit': bytes_limit
                    }
                },
                'recheck_cached_data': 'open',
            })
         return dataset_future.result()



def create_tensor(arr_shape, fpath=None, kvstore=None, driver='zarr3', dtype='float32', fill_value=0, 
                       chunk_shape=[64, 64, 64], shard_shape=None, res=[1,1,1], scale=0, codecs=None, index_codecs=None, sharded=False, shard_factor=4):
    """Create a tensorstore object, with optional setting of array
       driver: Type of file, including zarr, n5, precomputed
       store: Type of source, including file, in-memory, s3
       AWS Key, AWS_Secret_Key: Only applicable to s3 store
    """
    if 'int' in str(dtype):
        fill_value=0

     # If kvstore is not provided, create it from fpath
    if kvstore is None:
        kvstore = create_kvstore(fpath, store='file', AWS_param=None)

    if driver == 'zarr':
        out_arr = ts.open({
            "driver": "zarr",
            "kvstore": kvstore,
            "key_encoding": ".",
            "metadata": {
                "shape": list(arr_shape),
                "chunks": chunk_shape,
                "order": "C",
                "compressor": codecs
            },
            "dtype":dtype
        },
        fill_value=fill_value,
        create=True,  # this is what makes it a new one
        delete_existing=False  # optional: overwrite any existing array
        ).result()

    if driver == 'zarr3':
        meta = {
            "driver": "zarr3",
            "kvstore": kvstore,
            "metadata": {
                "shape": list(arr_shape),
                "chunk_grid": {"name": "regular", "configuration": {"chunk_shape": chunk_shape}},
                "data_type": dtype,
                "codecs": []
            }
        }

        if codecs:
            meta['metadata']['codecs'] = [codecs]
        if index_codecs:
            meta['metadata']['index_codecs'] = [index_codecs]

        if sharded == True:
            if not shard_shape:
                shard_shape = list(np.array(chunk_shape[:-3] + [x * (shard_factor) for x in chunk_shape[-3:]]))
            meta['metadata']['chunk_grid']['configuration']['chunk_shape']=shard_shape
            shard_meta = {
                    "name": "sharding_indexed",
                    "configuration": {
                        "chunk_shape": chunk_shape,
                        "codecs": [],
                        "index_codecs": [],
                        "index_location": "end"
                            }
                        }
            meta['metadata']['codecs'] = [shard_meta]

            if codecs:
                meta['metadata']['codecs'][0]['configuration']['codecs'] = [codecs]
            if index_codecs:
                meta['metadata']['codecs'][0]['configuration']['index_codecs'] = [index_codecs]
            
        out_arr =ts.open(meta,
        fill_value = 0,
        create=True,  
        delete_existing=False 
        ).result()

    if driver == 'n5':
        fill_value=None if driver=='n5' else fill_value
        out_arr = ts.open({
         'driver': driver,
         'kvstore': kvstore,
         },
         dtype=dtype,
         fill_value=fill_value,
         chunk_layout=ts.ChunkLayout(chunk_shape=chunk_shape),
         
         create=True,
         shape=list(arr_shape)).result()

    if driver == 'neuroglancer_precomputed':
        arr_shape=list(arr_shape)+[1] if len(arr_shape)==3 else arr_shape
        out_arr = ts.open(
                    {
                        "driver": "neuroglancer_precomputed",
                        "kvstore": kvstore,
                        "scale_metadata": {
                            "resolution": res,
                            "chunk_size": list(chunk_shape),
                            "encoding": "raw",
                            "key": "s" + str(scale)
                        }
                    },
                    create=True,
                    dtype=dtype,
                    domain=ts.IndexDomain(
                        shape=list(list(arr_shape)),
                    )).result()

    return out_arr

# Add cutout capability
import matplotlib.pyplot as plt

import gunpowder as gp
from gunpowder.ext import ZarrFile
from gunpowder.batch import Batch
from gunpowder.coordinate import Coordinate
from gunpowder.profiling import Timing
from gunpowder.roi import Roi
from gunpowder.array import Array
from gunpowder.array_spec import ArraySpec
from gunpowder.provider_spec import ProviderSpec

#from zarr._storage.store import BaseStore
#from zarr import N5Store, N5FSStore

import numpy as np
from collections.abc import MutableMapping
from typing import Union
import warnings
import logging
import copy
import torch 
import os
from datetime import datetime
import itertools
from functools import lru_cache

import tensorstore as ts

logger = logging.getLogger(__name__)

class TensorStoreSource(gp.ZarrSource):

    def __init__(self, tensorstore=None, array_specs=None, channels_first=True, add_margin=None):
        if array_specs is None:
            self.array_specs = {}
        else:
            self.array_specs = array_specs

        self.channels_first = channels_first
        self.tensorstore = tensorstore
        self.add_margin = add_margin
        self.shape = next(iter(self.tensorstore.values())).shape

    def _get_offset(self, dataset):
        if "offset" not in dataset.attrs:
            return None

        if self._rev_metadata():
            return Coordinate(dataset.attrs["offset"][::-1])
        else:
            return Coordinate(dataset.attrs["offset"])

    def _rev_metadata(self):
        with ZarrFile(self.store, mode="a") as store:
            return isinstance(store.chunk_store, N5Store) or isinstance(store.chunk_store, N5FSStore)

    def setup(self):
        for array_key, tensorstore in self.tensorstore.items():
            spec = self.__read_spec(array_key, tensorstore)
            self.provides(array_key, spec, tensorstore)

    def provides(self, key, spec, tensorstore):
        """Introduce a new output provided by this :class:`BatchProvider`."""
        name = 'TensorStoreSource[' + str(tensorstore.kvstore.path) + ']'
        logger.debug("Current spec of %s:\\n%s", name, self.spec)

        if self.spec is None:
            self._spec = ProviderSpec()

        assert (key not in self.spec), "Node %s is trying to add spec for %s, but is already provided." % (type(self).__name__, key)

        self.spec[key] = copy.deepcopy(spec)
        self.provided_items.append(key)

        logger.debug("%s provides %s with spec %s", name, key, spec)


    def __read_spec(self, array_key, tensorstore):
        dataset = tensorstore

        if array_key in self.array_specs:
            spec = self.array_specs[array_key].copy()
        else:
            spec = ArraySpec()

        if spec.voxel_size is None:
            voxel_size = Coordinate((1,) * len(dataset.shape))
            logger.warning(
                "WARNING: File %s does not contain resolution information for %s, voxel size has been set to %s. This might not be  you want.",
                tensorstore.kvstore.path,
                array_key,
                spec.voxel_size,
            )

        spec.voxel_size = voxel_size
        self.ndims = len(spec.voxel_size)

        if spec.roi is None:
            #offset = self._get_offset(dataset) RETURN TO THIS!
            offset = None
            if offset is None:
                offset = Coordinate((0,) * self.ndims)

            if self.channels_first:
                shape = Coordinate(dataset.shape[-self.ndims :])
            else:
                shape = Coordinate(dataset.shape[: self.ndims])

            spec.roi = Roi(offset, shape * spec.voxel_size)
        

        if spec.dtype is not None:
            assert spec.dtype == dataset.dtype.name, (
                "dtype %s provided in array_specs for %s, but differs from dataset dtype %s"
                % (self.array_specs[array_key].dtype, array_key, dataset.dtype.name)
            )
        else:
            spec.dtype = dataset.dtype.name

        if spec.interpolatable is None:
            spec.interpolatable = np.issubdtype(spec.dtype, np.floating) or (spec.dtype == np.uint8)
            logger.warning(
                "WARNING: You didn't set 'interpolatable' for %s. Based on the dtype %s, it has been set to %s. This might not be  you want.",
                array_key,
                spec.dtype,
                spec.interpolatable,
            )

        return spec

    def name(self):
        return 'TensorStoreSource[' + list(self.tensorstore.values())[0].kvstore.path + ']'


    def __read(self, data_file, roi):
        c = len(data_file.shape) - self.ndims

        slices = roi.to_slices()

        if self.add_margin:
            slices = tuple(
                    slice(
                        max(0, s.start - self.add_margin) if s.start != 0 else 0,
                        min(self.shape[i], s.stop + self.add_margin),
                        s.step
                    )
                    for i, s in enumerate(slices))


        if self.channels_first:
            array = data_file[(slice(None),) * c + slices].read().result()
        else:
            array = data_file[slices + (slice(None),) * c].read().result()
            array = np.transpose(array, axes=[i + self.ndims for i in range(c)] + list(range(self.ndims)))


        return array


    def provide(self, request):
        timing = Timing(self)
        timing.start()

        batch = Batch()

        for akey, tensorstore in self.tensorstore.items():
            for array_key, request_spec in request.array_specs.items():
                logger.debug("Reading %s in %s...", array_key, request_spec.roi)

                voxel_size = self.spec[array_key].voxel_size

                # scale request roi to voxel units
                dataset_roi = request_spec.roi / voxel_size

                # shift request roi into dataset
                dataset_roi = dataset_roi - self.spec[array_key].roi.offset / voxel_size

                # create array spec
                array_spec = self.spec[array_key].copy()
                array_spec.roi = request_spec.roi
                array = self.__read(tensorstore, dataset_roi)
                
                #if self.add_margin:
                    #nshape = array.shape
                    #dataset_roi.shape = nshape
                    #array_spec.roi.shape = nshape
                    #request_spec.roi = array_spec.roi
                    
                # add array to batch
                batch.arrays[array_key] = Array(array, array_spec)

        logger.debug("done")

        timing.stop()
        batch.profiling_stats.add(timing)

        return batch



class ContrastAdjustWrite(gp.BatchFilter):
    def __init__(self, input_key, output_key, input_arr, output_arr, int_range=None, version='range', mask=None, dsfactor=1, add_margin=None, depth=.9):
        self.input_key = input_key
        self.output_key = output_key
        self.int_range = int_range
        self.version = version
        self.out_array = output_arr
        self.in_array = input_arr
        self.write_objects = []
        self.mask = mask
        self.dsfactor = dsfactor
        self.add_margin=add_margin
        self.depth=.6

    def setup(self):
        pass

    def prepare(self, request):
        deps = gp.BatchRequest()
        deps[self.input_key] = request[self.output_key].copy()
        return deps

    def process(self, batch, request):
        roi = batch.arrays[self.input_key].spec.roi
        slices = roi.to_slices()
        if self.add_margin:
            slices = tuple(
                    slice(
                        max(0, s.start - self.add_margin) if s.start != 0 else 0,
                        min(self.out_array.shape[i], s.stop + self.add_margin),
                        s.step
                    )
                    for i, s in enumerate(slices))

        start = [s.start for s in slices]
        end = [s.stop for s in slices]
        _,_,x1, y1, z1 = start
        _,_,x2, y2, z2 = end
        
        if isinstance(self.mask, np.ndarray):
            ds_start, ds_end = np.ceil(np.array(start) / self.dsfactor).astype(int), np.ceil(np.array(end) / self.dsfactor).astype(int)
            print(ds_start,ds_end)
            dx1, dy1, dz1 = ds_start[-3:]
            dx2, dy2, dz2 = ds_end[-3:]

            if np.all(self.mask[0,0,dx1:dx2,dy1:dy2,dz1:dz2] > 0):
                return
    
        input_data = batch[self.input_key].data
        p1, p2 = np.percentile(input_data, self.int_range)

        #print(input_data.shape, start,end)
        
        if np.any(input_data) == True:
            if len(self.in_array.shape) ==5:
                input_data = input_data[0,0,:,:,:]
            scale = 1.0 / (p2 - p1) if p2 > p1 else 1.0
            output_data = np.clip((input_data - p1) * scale, 0, 1)
            output_data = (output_data * 255)

            if len(self.in_array.shape) ==5:
                try:
                    self.write_objects.append([[x1,x2,y1,y2,z1,z2], output_data])
                except:
                    pass
            else:
                self.write_objects.append([[x1,x2,y1,y2,z1,z2], output_data])

    def get_write_objects(self):
        return self.write_objects

    def clear_write_objects(self):
        self.write_objects = []

def no_neg(value):
    return value if value >= 0 else 0

@lru_cache(maxsize=10)
def make_mask(shape, depth=1):
    min_dim = min(shape)
    out = np.ones((min_dim,min_dim,min_dim))
    layers = int(min_dim*(depth/2))
    intervals = np.linspace(0, .8, layers)
    
    for ind, inter in enumerate(intervals):
        out[ind,:,:] = inter
        out[min_dim-1-ind,:,:] = inter
    
    y_swap = np.transpose(out.copy(), (1, 0, 2))  
    z_swap = np.transpose(out.copy(), (2, 1, 0))

    out = np.minimum(out, y_swap.copy())
    out = np.minimum(out,  z_swap.copy())

    if (shape == (shape[0],) * len(shape)) == False:
        x1, y1, z1 = out.shape
        x2, y2, z2 = shape
        
        x = np.linspace(0, x1 - 2, x2).astype(int)
        y = np.linspace(0, y1 - 2, y2).astype(int)
        z = np.linspace(0, z1 - 2, z2).astype(int)
        out = ((out[np.ix_(x, y, z)]))

    return out

def perimeter_weighted_blend(array1, array2, depth=.5):
    weight_map = make_mask(array1.shape, depth)
    return (array1 * (1 - weight_map) + array2 * (weight_map))


def create_chunked_dims(arr_shape, chunk_size):
    # Ensure chunk_size is appropriate for the arr_shape length
    if len(arr_shape) != len(chunk_size):
        raise ValueError("arr_shape and chunk_size must have the same number of dimensions")

    # Get indexing combinations
    start_indices = []
    end_indices = []

    for dim_size, chunk in zip(arr_shape, chunk_size):
        # Generate the start indices for each chunk
        start_indices.append(list(range(0, dim_size, chunk)))
        # Generate the end indices for each chunk, ensuring not to exceed the array size
        end_indices.append([min(dim_size, start + chunk) for start in start_indices[-1]])

    # Create all combinations of start and end indices across all dimensions
    start = [list(item) for item in itertools.product(*start_indices)]
    end = [list(item) for item in itertools.product(*end_indices)]

    return start, end

def create_overlap_chunks(start, end, overlap=32):
    new_start = []
    new_end = []
    s = np.array(start)
    e = np.array(end)

    arrays = [np.array([overlap,0,0]),np.array([0,overlap,0]),np.array([0,0,overlap]),np.array([overlap,0,overlap]),
              np.array([0,overlap,overlap]),np.array([overlap,overlap,0]), np.array([overlap,overlap,overlap])]

    new_start.append(list(s))
    new_end.append(list(e))
    for arr in arrays:
        new_start.append(list(s+arr))
        new_end.append(list(e+arr))
        
    return [new_start,new_end]

from datetime import datetime
import json
import time

def adjust_contrast_gunpowder(input_arr, output_arr, iter_size=(64,64,64), batch_size=3, cutout=None, mask_file=None, preprocess={'method':'percentile','values':[96,97]}, dsfactor=1, add_margin=0, depth=.7):

    mask=None
    if mask_file:
        mask = open_tensor(fpath=mask_file).read().result()
        print('mask', mask.shape)
    
    raw = gp.ArrayKey('RAW')
    source = TensorStoreSource(
        {
            raw: input_arr
        },
        {
            raw: gp.ArraySpec(interpolatable=True)
        }, add_margin=add_margin)


    if add_margin:
        iter_size = tuple(np.array(iter_size) + add_margin)
    print(iter_size)
    
    start_req = (0,0,0)
    if len(input_arr.shape) == 5:
        iter_size = (1,1,) + iter_size
        start_req = (0,0,0,0,0)
    chunk_size = batch_size*(np.array(iter_size))
    iter_coord = gp.Coordinate(iter_size)

    # Define the scan request with overlap
    scan_request = gp.BatchRequest()
    scan_request[raw] = gp.Roi(start_req, iter_coord)
    scan = gp.Scan(scan_request, num_workers=0)
    
    
    #create chunks
    start, end = create_chunked_dims(arr_shape=input_arr.shape, chunk_size=chunk_size)
    start_new, end_new = [], []
    
    if cutout:
        x1, x2, y1, y2, z1, z2 = cutout
        for i, (s, e) in enumerate(zip(start, end)):
            offset = np.array([x1,y1,z1])
            s, e = np.array(s[-3:])+offset, np.array(e[-3:])+offset
            if (s[0] <= x2 and s[1] <= y2 and s[2] <= z2):
                e[-3:] = np.minimum(np.array([x2,y2,z2])+(iter_size[-1]/2), np.array(e[-3:]))                             
                start_new.append(s)
                end_new.append(e)
                    
        start, end = start_new, end_new
        start_new, end_new = [], []
    
    
    og_start, og_end = [] , []
    for i in range(len(start)):
        sover, eover = create_overlap_chunks(start[i][-3:], end[i][-3:], overlap=int(iter_size[-1]/2))
        og_start += [sover[0]]
        og_end += [eover[0]]
        start_new += sover[1:]
        end_new += eover[1:]
    
    start_new = og_start #+ start_new
    end_new = og_end #+ end_new
         
    start,end = [],[]
    for i in range(len(start_new)):
        if len(input_arr.shape) == 5:
            start_new[i] = [0,0]+start_new[i]
            end_new[i] = [1,1]+end_new[i]
        start_new[i], end_new[i] = np.minimum(start_new[i], np.array(input_arr.shape)), np.minimum(end_new[i], np.array(input_arr.shape))
        
        dif = np.array(end_new[i]) - np.array(start_new[i])
        if np.any(dif[-3:] < iter_size[-1]) == False:
            new = np.floor((np.array(end_new[i][-3:])-np.array(start_new[i][-3:])) / iter_size[-1]).astype(int)*iter_size[-1]
            x,y,z = (np.array(new)+np.array(start_new[i][-3:])).tolist()
            end_new[i][-3:] = [x,y,z]
            
            start.append(start_new[i])
            end.append(end_new[i])

        
    if len(start) == 0:
        print('Batch_size needs to be lowered to accommodate the cutout size.')
        return
    
    method, values = preprocess['method'], preprocess['values']
    contrast = ContrastAdjustWrite(raw,raw,input_arr,output_arr,int_range=values,version=method, mask=mask, dsfactor=dsfactor, add_margin=add_margin)
        
    # Build the pipeline with Scan
    pipeline = (
            source +
            contrast +
            scan)

    stime = datetime.now()

    with gp.build(pipeline):
        for ind,i in enumerate(range(len(start))):
            print(start[i], end[i])
            arr = np.array(end[i])-np.array(start[i])
            total_roi = gp.Roi(start[i], arr)
    
            # Create a request for the entire volume
            request = gp.BatchRequest()
            request[raw] = total_roi
            
            # Request the batch
            batch = pipeline.request_batch(request)
                
            # Retrieve the list of write objects and write them
            write_objects = contrast.get_write_objects()
            if len(write_objects) > 0:
                indices = [item[0] for item in write_objects]
                x1,x2,y1,y2,z1,z2 = [max(slot) for slot in zip(*indices)]
                mx1,mx2,my1,my2,mz1,mz2 = [min(slot) for slot in zip(*indices)]
                    
                if len(output_arr.shape) == 5:
                    temp_shape = [1,1] + [x2-mx1,y2-my1,z2-mz1]
                    
                success = False
                max_retries = 10
                for attempt in range(max_retries):                                                            

                    temp_arr = output_arr[:,:,mx1:x2,my1:y2,mz1:z2].read().result()
                        
                    for write in write_objects:
                        ox1,ox2,oy1,oy2,oz1,oz2 = write[0]
                        arr2 = temp_arr[0,0,ox1-mx1:ox2-mx1, oy1-my1:oy2-my1, oz1-mz1:oz2-mz1]
                        write_data = perimeter_weighted_blend(arr2, write[1], depth=depth)#.astype('uint8')
                        temp_arr[:,:,ox1-mx1:ox2-mx1, oy1-my1:oy2-my1, oz1-mz1:oz2-mz1] = write_data[None, None, :]
                    
                
                    try:
                        if len(input_arr.shape) == 5:
                            output_arr[:, :, mx1:x2, my1:y2, mz1:z2].write(temp_arr[:, :, :, :, :]).result()
                        else:
                            output_arr[mx1:x2, my1:y2, mz1:z2].write(temp_arr[:, :, :]).result()
                        success = True
                        break  # Exit loop if successful
                    except Exception as e:
                        print(f"Attempt {attempt+1} failed: {e}")
                        if attempt < max_retries - 1:
                            time.sleep(5)  # Wait before next retry
                

                contrast.clear_write_objects()
                etime = datetime.now()
                print(i, etime - stime)

class ContrastParameters(argschema.ArgSchema):
    input_path = argschema.fields.String(required=True)
    output_path = argschema.fields.String(required=True)
    AWS_key = argschema.fields.String(required=False, default=None, allow_none=True)
    AWS_sec_key = argschema.fields.String(required=False, default=None, allow_none=True)
    region = argschema.fields.String(required=False, default='us-west-2')
    endpoint = argschema.fields.String(required=False, default=None, allow_none=True)
    profile = argschema.fields.String(required=False, default=None, allow_none=True)
    cutout = argschema.fields.List(argschema.fields.Int(),required=False, default=None, allow_none=True)
    dsfactor = argschema.fields.Int(required=False, default=1, allow_none=True)
    mask_path = argschema.fields.String(required=False, allow_none=True, default='None')


class ContrastModule(argschema.ArgSchemaParser):
    default_schema = ContrastParameters

    def run(self):
        for key, value in self.args.items():
            if value == 'None':
                self.args[key] = None
                
        kvstore = None
        if self.args['profile']:
            AWS_param = AWS_Parameters(profile=self.args['profile'], region=self.args['region'], endpoint_url=self.args['endpoint'])      
            kvstore = create_kvstore(fpath=self.args['output_path'], store='s3', AWS_param=AWS_param)              
                            
        if self.args['AWS_key']:
            AWS_param = AWS_Parameters(region=self.args['region'], endpoint_url=self.args['endpoint'])
            AWS_param.add_credentials(access_key_id=self.args['AWS_key'], secret_access_key=self.args['AWS_sec_key'])
            kvstore = create_kvstore(fpath=self.args['output_path'], store='s3', AWS_param=AWS_param)
            
        
        input_arr = open_tensor(self.args['input_path'], bytes_limit= 100_000_000, driver='zarr')

        try:
            output_arr = create_tensor(fpath=self.args['output_path'], arr_shape=input_arr.shape, dtype='uint8', chunk_shape=[1, 1, 64, 64, 64], driver='zarr3', codecs={"name": "blosc", "configuration": {"cname": "lz4", "clevel": 4}}, sharded=True, kvstore=kvstore, shard_factor=16)
        except:
            output_arr = open_tensor(self.args['output_path'], bytes_limit= 100_000_000, driver='zarr', kvstore=kvstore)      
                                                                                                                                           
        adjust_contrast_gunpowder(input_arr, output_arr, iter_size=(32,32,32), batch_size=5, cutout=self.args['cutout'], preprocess={'method':'percentile','values':[5,99]}, mask_file=self.args['mask_path'], dsfactor=self.args['dsfactor'], add_margin=32)
                                       


if __name__ == "__main__":
    mod = ContrastModule()
    mod.run()

__all__ = [
    "ContrastModule",
    "ContrastParameters"]