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
from zarr._storage.store import BaseStore
from zarr import N5Store, N5FSStore

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
import tensorstore as ts
import time

from ac_segmentation.utils.tensorstore import open_tensor, create_tensor
import ac_segmentation.neurotorch.nets.RSUNet
RSUNet = ac_segmentation.neurotorch.nets.RSUNet.RSUNet

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


class ContrastAdjust(gp.BatchFilter):
    def __init__(self, input_key, output_key, int_range=None, version='range'):
        self.input_key = input_key
        self.output_key = output_key
        self.int_range = int_range
        self.version = version

    def setup(self):
        pass

    def prepare(self, request):
        # Ensure the input array is requested
        deps = gp.BatchRequest()
        deps[self.input_key] = request[self.output_key].copy()
        return deps

    def process(self, batch, request):
        # Get the input data
        input_data = batch[self.input_key].data

        # Apply the contrast adjustment function with the specified parameters
        if self.int_range:
            r1,r2 = self.int_range
            if self.version == 'range':
                adjusted_data = lut_preprocess_array_minmax(input_data, r1, r2)

            if self.version == 'percentile':
                p1, p2 = np.percentile(input_data, self.int_range)
                scale = 1.0 / (p2 - p1) if p2 > p1 else 1.0
                adjusted_data = np.clip((input_data - p1) * scale, 0, 1)
                adjusted_data = (adjusted_data * 255).astype(str(input_data.dtype))

        # Create a new batch with the adjusted data
        spec = batch[self.input_key].spec.copy()
        spec.roi = request[self.output_key].roi.copy()

        # Create a new array
        adjusted_array = gp.Array(adjusted_data, spec)

        # Store it in the batch
        batch = gp.Batch()
        batch[self.output_key] = adjusted_array
        
        return batch


class ApplyModel(gp.BatchFilter):
    def __init__(self, model, input_key, ts_array, device, mask=None, dsfactor=1):
        self.model = model
        self.input_key = input_key
        self.ts_array = ts_array
        self.write_objects = []
        self.device = device
        self.mask = mask
        self.dsfactor = dsfactor

    def process(self, batch, request):
        # Get the input data
        input_data = batch[self.input_key].data
        roi = batch.arrays[self.input_key].spec.roi
        start, end = list(roi.begin[-3:]), list(roi.end[-3:])
        x1, y1, z1 = start
        x2, y2, z2 = end
        og_shape = input_data.shape

        if isinstance(self.mask, np.ndarray):
            ds_start, ds_end = np.ceil(np.array(start) / self.dsfactor).astype(int), np.ceil(np.array(end) / self.dsfactor).astype(int)
            dx1, dy1, dz1 = ds_start
            dx2, dy2, dz2 = ds_end

            if np.all(self.mask[0,0,dx1:dx2,dy1:dy2,dz1:dz2] > 0):
                return

        # CHECK THISSSSS!! 
        if input_data.dtype != np.int16:
            input_data = input_data.astype(np.int16)
        if len(input_data.shape)<5:
            x,y,z = input_data.shape
            input_data = input_data.reshape(1, 1, x, y, z)
            
        # Convert input data to a tensor
        input_tensor = torch.from_numpy(input_data).float().to(self.device)

        # Run the model
        with torch.inference_mode():
            output_tensor = self.model(input_tensor)

        # Convert output tensor to probability map
        output_data = output_tensor[0].data.cpu()
        output_data = torch.special.expit(output_data).numpy()

        # Write predictions to TensorStore
        roi = batch.arrays[self.input_key].spec.roi
        offset = roi.get_begin()[-3:]
        try:
            if len(self.ts_array.shape) == 5:
                arr_blend = self.ts_array[:,:,x1:x2,y1:y2,z1:z2].read().result()
            else:
                output_data = output_data[0,0,:,:,:]
                arr_blend = self.ts_array[x1:x2,y1:y2,z1:z2].read().result()
                
            if np.isneginf(arr_blend).any():
                arr_blend[arr_blend == -np.inf] = 0
        
        except:
            arr_blend = np.zeros(output_data.shape)
            if len(self.ts_array.shape) == 3:
                arr_blend = arr_blend[0,0,:,:,:]
            
        arr_blend += output_data
        self.write_objects.append([[x1,x2,y1,y2,z1,z2], arr_blend])
        
    def get_write_objects(self):
        return self.write_objects

    def clear_write_objects(self):
        self.write_objects = []
        
        
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
    s = np.array(start[-3:])
    e = np.array(end[-3:])
    
    new_start.append(list(s))
    new_start.append(list(s+np.array([32,0,0])))
    new_start.append(list(s+np.array([0,32,0])))
    new_start.append(list(s+np.array([0,0,32])))

    new_end.append(list(e))
    new_end.append(list(e+np.array([32,0,0])))
    new_end.append(list(e+np.array([0,32,0])))
    new_end.append(list(e+np.array([0,0,32])))

    return [new_start,new_end]

def lut_preprocess_array_minmax(arr, min_int=None, max_int=None):
    dtype =  str(arr.dtype)
    arr_max = int(arr.max())
    if not max_int:
        max_int=arr_max
    max_int=int(max_int)
    lut = np.empty(int(arr_max + max_int), dtype="uint8")
    if min_int:
        lut[:min_int] = 0
    lut[max_int:] = 255
    lut[:max_int] = np.round(np.arange(max_int) * (255 / max_int))
    if 'int' not in str(arr.dtype):
        arr = arr.astype('int16')
    return lut[arr].astype(dtype)
    
    
from ac_segmentation.utils.tensorstore import open_tensor, create_tensor, create_kvstore, AWS_Parameters
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
                shard_shape = list(np.array(chunk_shape)*4)
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
    
    
    
    
def segment_gunpowder(input_arr, output_arr, checkpoint, iter_size=(64,64,64), batch_size=5, cutout=None, gpu_device=None, cpus=20, preprocess={'method':'percentile','values':[96,97]}, mask_file=None, dsfactor=1):
    mask=None
    if mask_file:
        mask = open_tensor(fpath=mask_file).read().result()
        print('mask', mask.shape)
    
    if int(cpus) > int(os.cpu_count()):
        cpus = os.cpu_count()
    torch.set_num_threads(cpus) 
    
    # Set-up model
    device = torch.device("cuda:{}" .format(gpu_device) if gpu_device is not None else "cpu")
    model = RSUNet()
    
    model = model.to(device).eval()
    model.load_state_dict(torch.load(checkpoint, map_location=device))

    start_req = (0,0,0)
    if len(input_arr.shape) == 5:
        iter_size = (1,1,) + iter_size
        start_req = (0,0,0,0,0)
    chunk_size = batch_size*np.array(iter_size)
    
    raw = gp.ArrayKey('RAW')
    source = TensorStoreSource(
        {
            raw: input_arr
        },
        {
            raw: gp.ArraySpec(interpolatable=True)
        })

    # Define the chunk size
    iter_coord = gp.Coordinate(iter_size) 
    
    # Define the scan request with overlap
    scan_request = gp.BatchRequest()
    scan_request[raw] = gp.Roi(start_req, iter_coord)
    scan = gp.Scan(scan_request)
    
    # Create the ApplyModel instance
    apply_model = ApplyModel(model, raw, output_arr, device, mask=mask, dsfactor=dsfactor)
    
    # Build the pipeline with Scan
    method, values = preprocess['method'], preprocess['values']
    pipeline = (
        source +
        ContrastAdjust(raw,raw,values,version=method) +
        apply_model +
        scan
    )
    
    stime = datetime.now()
    
    #create chunks
    start, end = create_chunked_dims(arr_shape=input_arr.shape, chunk_size=chunk_size)
    start_new, end_new = [], []

    if cutout:
        x1, x2, y1, y2, z1, z2 = cutout
        for i, (s, e) in enumerate(zip(start, end)):
            offset = np.array([x1,y1,z1])
            s, e = np.array(s[-3:])+offset, np.array(e[-3:])+offset
            if (s[0] <= x2 and s[1] <= y2 and s[2] <= z2):
                if (e[0] <= x2 and e[1] <= y2 and e[2] <= z2):
                    start_new.append(s)
                    end_new.append(e)
                else:
                    e[-3:] = np.minimum(np.array([x2,y2,z2]), np.array(e[-3:])) + iter_size[-1]
                    start_new.append(s)
                    end_new.append(e)
                    
        start, end = start_new, end_new
        start_new, end_new = [], []
        
    for i in range(len(start)):
        sover, eover = create_overlap_chunks(start[i][-3:], end[i][-3:], overlap=int(iter_size[-1]/2))
        start_new += sover
        end_new += eover
    
    for i in range(len(start_new)):
        if len(input_arr.shape) == 5:
            start_new[i] = [0,0]+start_new[i]
            end_new[i] = [1,1]+end_new[i]
        start_new[i], end_new[i] = np.minimum(start_new[i], np.array(input_arr.shape)), np.minimum(end_new[i], np.array(input_arr.shape))
        dif = np.array(end_new[i]) - np.array(start_new[i])
        for j in range(1,4):
            if dif[-j] < iter_size[-j]:
                start_new[i][-j] = end_new[i][-j]-iter_size[-j]

        new = np.floor((np.array(end_new[i][-3:])-np.array(start_new[i][-3:])) / iter_size[-1]).astype(int)*iter_size[-1]
        x,y,z = (np.array(new)+np.array(start_new[i][-3:])).tolist()
        end_new[i][-3:] = [x,y,z]
        
    if len(start) == 0:
        print('Batch_size needs to be lowered to accommodate the cutout size.')
        return
    
    #run pipeline    
    with gp.build(pipeline):
        for i in range(len(start_new)):
            arr = np.array(end_new[i])-np.array(start_new[i])
            total_roi = gp.Roi(start_new[i], arr)

            print(i,arr)
                
            # Create a request for the entire volume
            request = gp.BatchRequest()
            request[raw] = total_roi
        
            # Request the batch
            batch = pipeline.request_batch(request)
    
            # Retrieve the list of write objects and write them
            write_objects = apply_model.get_write_objects()
            if len(write_objects) > 0:
                indices = [item[0] for item in write_objects]
                x1,x2,y1,y2,z1,z2 = [max(slot) for slot in zip(*indices)]
                mx1,mx2,my1,my2,mz1,mz2 = [min(slot) for slot in zip(*indices)]
                    
                if len(output_arr.shape) == 5:
                    temp_shape = [1,1] + [x2-mx1,y2-my1,z2-mz1]
        
                temp_arr = np.zeros(temp_shape).astype(output_arr.dtype.name)
                    
                for write in write_objects:
                    ox1,ox2,oy1,oy2,oz1,oz2 = write[0]
                    temp_arr[:,:,ox1-mx1:ox2-mx1, oy1-my1:oy2-my1, oz1-mz1:oz2-mz1] = write[1][None, None, :]
                
                success = False
                max_retries = 10
                
                for attempt in range(max_retries):
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
        
                apply_model.clear_write_objects()
    
    etime = datetime.now()
    print(etime-stime)
    
    #output seg card
    compute = {'GPUs': gpu_device} if gpu_device else {'CPUs': cpus}
    seg_card = {'date':datetime.today().strftime('%Y-%m-%d'),
                'paths':{'inpath':input_arr.kvstore.path,'outpath':output_arr.kvstore.path}, 
                'preprocessing':{'method':method,'values':values}, 
                'compute':compute,
                'time_lapse':etime-stime}

    with open(os.path.join(output_arr.kvstore.path, "seg_card.txt"), 'w') as f:
        f.write(str(seg_card))
    
    return seg_card
    
    

import argschema
import os
import pathlib
import docker
import torch
import ast


class CloudOptions(argschema.schemas.DefaultSchema):
    AWS_key = argschema.fields.String(required=False, default=None, allow_none=True)
    AWS_sec_key = argschema.fields.String(required=False, default=None, allow_none=True)
    region = argschema.fields.String(required=False, default='us-east-1')
    endpoint = argschema.fields.String(required=False, default=None, allow_none=True)
    profile = argschema.fields.String(required=False, default=None, allow_none=True)
    

class SegmentZarrParameters(argschema.ArgSchema):
    input_zarr = argschema.fields.String(required=True)
    weights_file = argschema.fields.InputFile(required=True)
    probability_output = argschema.fields.String(required=True)         
    filter_max_intensity = argschema.fields.Int(required=False, default=30000, allow_non=True)
    rescale_perc = argschema.fields.String(allow_none=True, default='[96,97]')
    cloud_options = argschema.fields.Nested(
        CloudOptions, required=False)
    bound_box = argschema.fields.List(argschema.fields.Int(),required=False, default=None, allow_none=True)
    dsfactor = argschema.fields.Int(required=False, default=1, allow_none=True)
    mask_path = argschema.fields.String(required=False, allow_none=True, default='None')
    
class SegmentZarrModule(argschema.ArgSchemaParser):
    default_schema = SegmentZarrParameters
            
    @property
    def cloud_options(self):
        return self.args["cloud_options"]


    def run(self):

        try:
            cloud = self.cloud_options
        except:
            cloud = None
            
        for key, value in self.args.items():
            if value == "None":
                self.args[key] = None
            
        
        kvstore = None
        #if cloud:
            #if cloud['profile']:
                #AWS_param = AWS_Parameters(profile=cloud['profile'], region=cloud['region'], endpoint_url=cloud['endpoint'])      
                #kvstore = create_kvstore(fpath=self.args['probability_output'], store='s3', AWS_param=AWS_param)              
                            
            #if cloud['AWS_key']:
                #AWS_param = AWS_Parameters(region=cloud['region'], endpoint_url=cloud['endpoint'])
                #AWS_param.add_credentials(access_key_id=cloud['AWS_key'], secret_access_key=cloud['AWS_sec_key'])
                #kvstore = create_kvstore(fpath=self.args['probability_output'], store='s3', AWS_param=AWS_param)
                
        input_arr = open_tensor(os.path.join(self.args['input_zarr'].rstrip('/'),'0'), bytes_limit= 100_000_000, driver='zarr')
                
        try:
            output_arr = create_tensor(fpath=self.args['probability_output'], arr_shape=input_arr.shape, dtype='float32', chunk_shape=[1, 1, 64, 64, 64], driver='zarr3', codecs=None , sharded=False, kvstore=kvstore)
            
        except:
            output_arr = open_tensor(self.args['probability_output'], bytes_limit= 100_000_000, driver='zarr', kvstore=kvstore)      
                                                                                                                                                   
        if self.args['rescale_perc']:
            rescale = ast.literal_eval(self.args["rescale_perc"])
            preprocess = {'method':'percentile','values':rescale}
        else:
            preprocess = {'method':'range','values':[0,60000]}
        
        segment_gunpowder(input_arr, output_arr, self.args["weights_file"], iter_size=(64,64,64), batch_size=5, cutout=self.args["bound_box"], gpu_device=None, cpus=40, preprocess=preprocess, mask_file=self.args['mask_path'], dsfactor=self.args['dsfactor'])



if __name__ == "__main__":
    mod = SegmentZarrModule()
    mod.run()

__all__ = [
    "SegmentZarrModule",
    "SegmentZarrParameters"]
    
    