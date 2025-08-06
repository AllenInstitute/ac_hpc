import os
from ac_segmentation.postprocess.skeletonize_array import skeletonize_labeled_array_concurrent
import argschema
import pathlib
import docker
import torch
from ac_segmentation.utils.tensorstore import open_ZarrTensor,AWS_Parameters,create_kvstore
from ac_segmentation.utils.io import (write_cv_skels_iter_tar)



class CloudOptions(argschema.schemas.DefaultSchema):
    AWS_key = argschema.fields.String(required=False, default=None, allow_none=True)
    AWS_sec_key = argschema.fields.String(required=False, default=None, allow_none=True)
    region = argschema.fields.String(required=False, default='us-east-1')
    bucket = argschema.fields.String(required=False, default=None, allow_none=True)
    endpoint = argschema.fields.String(required=False, default=None, allow_none=True)
    profile = argschema.fields.String(required=False, default=None, allow_none=True)
     

class SkeletonizeProbabilitiesParameters(argschema.ArgSchema):
    input_zarr = argschema.fields.String(required=True)
    skeleton_output = argschema.fields.OutputFile(required=True)
    probability_threshold = argschema.fields.Float(
        required=False, default=0.05)
    label_size_threshold = argschema.fields.Int(required=False, default=80)
    cloud_options = argschema.fields.Nested(
        CloudOptions, required=False)
    n_jobs = argschema.fields.Int(required=False, default=10)
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
        if 'endpoint' in self.cloud_options:
            cloud = self.cloud_options
            if cloud['profile']:
                AWS_param = AWS_Parameters(profile=cloud['profile'], region=cloud['region'], endpoint_url=cloud['endpoint'])                    
                            
            if cloud['AWS_key']:
                AWS_param = AWS_Parameters(region=cloud['region'], endpoint_url=cloud['endpoint'])
                AWS_param.add_credentials(access_key_id=cloud['AWS_key'], secret_access_key=cloud['AWS_sec_key'])
                
            kvstore = create_kvstore(fpath=self.args["input_zarr"], store='s3', AWS_param=AWS_param) 
            array = open_ZarrTensor(kvstore=kvstore, driver='zarr3')
        
        else:
            array = open_ZarrTensor(fpath=self.args["input_zarr"], driver='zarr3')
            
        skels = skeletonize_labeled_array_concurrent(
            array=array,
            probability_threshold=self.args["probability_threshold"],
            label_size_threshold=self.args["label_size_threshold"],
            n_jobs=15
        )
        
        write_cv_skels_iter_tar(self.args["skeleton_output"], skels)
        
        self.output(self.args)


if __name__ == "__main__":
    mod = SkeletonizeProbabilitiesModule()
    mod.run()


__all__ = [
    "SkeletonizeProbabilitiesModule",
    "SkeletonizeProbabilitiesParameters"
]

    
    
            