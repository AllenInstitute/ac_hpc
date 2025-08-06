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
                       chunk_shape=[64, 64, 64], shard_shape=None, res=[1,1,1], scale=0, codecs=None, index_codecs=None, sharded=False):
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
                shard_shape = list(np.array(chunk_shape[:-3] + [x * 4 for x in chunk_shape[-3:]]))
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

import numpy as np
from collections.abc import MutableMapping
from typing import Union
import warnings
import logging
import copy
import torch 
import os
from datetime import datetime
import tensorstore as ts


logger = logging.getLogger(__name__)

class TensorStoreSource(gp.ZarrSource):

    def __init__(self, tensorstore=None, array_specs=None, channels_first=True):
        if array_specs is None:
            self.array_specs = {}
        else:
            self.array_specs = array_specs

        self.channels_first = channels_first
        self.tensorstore = tensorstore

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
                
                # add array to batch
                batch.arrays[array_key] = Array(self.__read(tensorstore, dataset_roi), array_spec)

        logger.debug("done")

        timing.stop()
        batch.profiling_stats.add(timing)

        return batch

    def __read(self, data_file, roi):
        c = len(data_file.shape) - self.ndims

        if self.channels_first:
            array = data_file[(slice(None),) * c + roi.to_slices()].read().result()
        else:
            array = data_file[roi.to_slices() + (slice(None),) * c].read().result()
            array = np.transpose(array, axes=[i + self.ndims for i in range(c)] + list(range(self.ndims)))

        return array

    def __read_spec(self, array_key, tensorstore):
        dataset = tensorstore

        if array_key in self.array_specs:
            spec = self.array_specs[array_key].copy()
        else:
            spec = ArraySpec()

        if spec.voxel_size is None:
            voxel_size = Coordinate((1,) * len(dataset.shape))
            logger.warning(
                "WARNING: File %s does not contain resolution information for %s, voxel size has been set to %s. This might not be what you want.",
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
                "WARNING: You didn't set 'interpolatable' for %s. Based on the dtype %s, it has been set to %s. This might not be what you want.",
                array_key,
                spec.dtype,
                spec.interpolatable,
            )

        return spec

    def name(self):
        return 'TensorStoreSource[' + list(self.tensorstore.values())[0].kvstore.path + ']'
        
        
        
import itertools
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
        
        
        
import tinybrain
class Downsample(gp.BatchFilter):
    def __init__(self, ds_factors, input_key, output_arr, dtype):
        self.ds_factors = ds_factors
        self.input_key = input_key
        self.write_objects = []
        self.dtype = dtype
        self.output_arr = output_arr

    def process(self, batch, request):
        # Get the input data
        
        input_data = batch[self.input_key].data
        if len(input_data.shape) == 5:
             input_data = batch[self.input_key].data[0,0,:,:,:]
             
        if np.all(input_data==0) == False:
            #output_data = tinybrain.downsample_with_averaging(input_data, factor=self.ds_factors)[0]
            output_data = tinybrain.downsample_with_averaging(input_data, factor=self.ds_factors)[0]
            if output_data.dtype != self.dtype:
                output_data = output_data.astype(self.dtype)
                
            # Write predictions to TensorStore
            roi = batch.arrays[self.input_key].spec.roi
            offset = roi.get_begin()
            og_shape = np.array(offset[-3:])
            dx,dy,dz = (og_shape/np.array(self.ds_factors)).astype(int)
    
            if len(self.output_arr.shape) == 3:
                write_obj = self.output_arr[dx:dx + output_data.shape[0],dy:dy + output_data.shape[1],dz:dz + output_data.shape[2]].write(output_data)
            else:
                write_obj = self.output_arr[0,0,dx:dx + output_data.shape[0],dy:dy + output_data.shape[1],dz:dz + output_data.shape[2]].write(output_data)
                
            self.write_objects.append(write_obj) 

    def get_write_objects(self):
        return self.write_objects

    def clear_objects(self):
        self.write_objects = []
        
        
def downsample_gunpowder(input_arr, output_arr, iter_size = (64,64,64), batch_size=5, dsfactors=(2,2,2), cutout=None):
    # Define ArrayKeys
    torch.set_num_threads(20) 
    raw = gp.ArrayKey('RAW')
    
    #create tensorstore arrays
    dtype = input_arr.dtype.name
    
    # Define the pipeline
    source = TensorStoreSource(
        {
            raw: input_arr
        },
        {
            raw: gp.ArraySpec(interpolatable=True)
        })
    
        
    chunk_size = tuple(np.array(iter_size)*batch_size)
    # Define the chunk size and overlap
    if len(input_arr.shape) == 5:
        iter_size = (1,1,) + iter_size
        chunk_size = (1,1,) + chunk_size
        start_req = (0,0,0,0,0)
    iter_size = np.minimum(np.array(iter_size),np.array(output_arr.shape))
    chunk_size = np.minimum(np.array(chunk_size),np.array(output_arr.shape))
    
    print(iter_size,chunk_size)
    
        
    if cutout:
        x1, x2, y1, y2, z1, z2 = cutout    
        chunk_size = ((np.minimum(np.array(chunk_size[-3:]),np.array([x2,y2,z2])-np.array([x1,y1,z1])))).astype(int).tolist()
        iter_size = ((np.minimum(np.array(iter_size[-3:]),np.array([x2,y2,z2])-np.array([x1,y1,z1])))).astype(int).tolist()
        if len(input_arr.shape) == 5:
            chunk_size = [1,1] + chunk_size
            iter_size = [1,1] + iter_size              
            
    # Request a batch and process it
    start,end = create_chunked_dims(arr_shape=input_arr.shape, chunk_size=chunk_size)
    start_new,end_new = [], []
                        
               
    if cutout:
        x1, x2, y1, y2, z1, z2 = cutout
        for i, (s, e) in enumerate(zip(start, end)):
            offset = np.array([x1,y1,z1])
            s, e = np.array(s[-3:])+offset, np.array(e[-3:])+offset
            if (s[0] <= x2 and s[1] <= y2 and s[2] <= z2):
                start_new.append(s.tolist())
                end_new.append(e.tolist())
                
    else:
        start_new,end_new = start,end
                    
    save = start_new[0]
    for i in range(len(start_new)):
        arr1,arr2 = np.array(start_new[i]),np.array(end_new[i])
        if np.any((arr2-arr1)[-3:] < np.array(iter_size[-3:])) == True:
            start_new[i] = np.minimum(arr1,save).tolist()
        else:
            save = arr1
    
    if cutout:
        if len(input_arr.shape) == 5: 
          for i in range(len(start_new)):
              start_new[i] = [0,0] + start_new[i]
              end_new[i] = [1,1] + end_new[i]
          
          
    iter_coord = gp.Coordinate(iter_size)
    
    # Define the scan request with overlap
    scan_request = gp.BatchRequest()
    scan_request[raw] = gp.Roi(start_req, iter_coord)
    scan = gp.Scan(scan_request) 
    
    
    # Create the downsample node
    downsample = Downsample(dsfactors, raw, output_arr, input_arr.dtype.name)
    
    # Build the pipeline with Scan
    pipeline = (
        source +
        downsample +
        scan)
            
        
    with gp.build(pipeline):
        stime = datetime.now()
        for i in range(len(start_new)):
            try:
                arr = np.array(end_new[i])-np.array(start_new[i])
                print(start_new[i], end_new[i], arr)
                total_roi = gp.Roi(start_new[i], arr)
            
                # Create a request for the entire volume
                request = gp.BatchRequest()
                request[raw] = total_roi
    
                # Request the batch
                batch = pipeline.request_batch(request)
                etime = datetime.now()
                print(etime-stime)
                write_objects = downsample.get_write_objects()
    
                for i,miparr in enumerate(write_objects):
                    miparr.result()
                downsample.clear_objects()
                
            except Exception as e:
                print(f'fail: {e}')



class DownsampleParameters(argschema.ArgSchema):
    input_path = argschema.fields.String(required=True)
    cutout = argschema.fields.List(argschema.fields.Int(),required=False, default=None, allow_none=True)


class DownsampleModule(argschema.ArgSchemaParser):
    default_schema = DownsampleParameters

    def run(self):
        for key, value in self.args.items():
            if value == 'None':
                self.args[key] = None
                
        fpath = self.args['input_path']
    
        for i in range(4,5):
            print(i)
            in_path = fpath+str(i)
            out_path = fpath+str(i+1)
        
            in_arr = open_tensor(fpath=in_path)
            
            
            mip_cutout = self.args['cutout']
            if self.args['cutout']:
                mip_cutout = tuple(np.ceil(np.array(self.args['cutout'])/(2**i)).astype(int).tolist())
            
            down_shape = tuple(np.ceil(np.array(in_arr.shape)/2).astype(int).tolist())
            iter_size = tuple(np.ceil(np.array([64, 64, 64])/(2**i)).astype(int))          
            
            print(i, i+1, down_shape, mip_cutout, iter_size)
                                    
            
            try:
                out_arr = create_tensor(fpath=out_path, arr_shape=down_shape, dtype='uint8', chunk_shape = [1,1,64,64,64], driver='zarr3', codecs=None , sharded=False)
            except:
                out_arr = open_tensor(fpath=out_path)
                
                
            downsample_gunpowder(in_arr, out_arr, batch_size=5 , cutout=mip_cutout,iter_size=(32,32,32)) #iter_size = iter_size)
                                                                                                                                                 


if __name__ == "__main__":
    mod = DownsampleModule()
    mod.run()

__all__ = [
    "DownsampleModule",
    "DownsampleParameters"]





