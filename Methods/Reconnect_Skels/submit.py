import os
import argschema
import pathlib
import navis
from acanalysis.skeleton_reconstruction.reconnect_skeletons import reconnect
from acanalysis.skeleton_reconstruction.util import write_navis_skels_tar


class CloudOptions(argschema.schemas.DefaultSchema):
    AWS_key = argschema.fields.String(required=False, default=None, allow_none=True)
    AWS_sec_key = argschema.fields.String(required=False, default=None, allow_none=True)
    region = argschema.fields.String(required=False, default='us-east-1')
    bucket = argschema.fields.String(required=False, default=None, allow_none=True)
    endpoint = argschema.fields.String(required=False, default=None, allow_none=True)
    profile = argschema.fields.String(required=False, default=None, allow_none=True)
     

class ReconnectParameters(argschema.ArgSchema):
    skels = argschema.fields.InputFile(required=True, metadata = {'description': 'Input skeletons, as navis objects, swc, or swc.gz'})
    out_file = argschema.fields.OutputFile(required=False, dump_default=None, metadata = {'description': 'Output file for reconnected skeletons'})
    cl = argschema.fields.InputFile(required=False, dump_default=None, allow_none=True,metadata = {'description': 'Model File'})
    sc = argschema.fields.InputFile(required=False, dump_default=None, allow_none=True, metadata = {'description': 'Scalar File'})    
    min_nodes = argschema.fields.Int(required=False, dump_default=10, description='Minimum skeleton node length')
    prob_thresh = argschema.fields.Float(required=False, dump_default=0.3, description='Minimum probability allowed for merge model prediction')
    downsample = argschema.fields.Int(required=False, dump_default=4, description='Factor for upsampling skeletons')
    query_dis = argschema.fields.Int(required=False, dump_default=20, description='Maximum query distance for matching end nodes')
    min_collin = argschema.fields.Float(required=False, dump_default=.7, description='Minimum collinearity for finding skeleton merge pairs')

    
class ReconnectModule(argschema.ArgSchemaParser):
    default_schema = ReconnectParameters

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
    
        
        skels, merges = reconnect(skels = self.args['skels'], cl=self.args['cl'], sc=self.args['sc'],
        min_nodes=self.args['min_nodes'], prob_thresh=self.args['prob_thresh'], downsample=self.args['downsample'], split=True, query_dis=self.args['query_dis'], min_collin=self.args['min_collin'], dis_end=0)
        
        
        skels = navis.NeuronList([skels,merges])
        
        skels, merges = reconnect(skels = skels, cl=self.args['cl'], sc=self.args['sc'],
        min_nodes=0, prob_thresh=self.args['prob_thresh'], downsample=None, split=False, query_dis=10, min_collin=self.args['min_collin'], dis_end=2)
        
        skels = navis.NeuronList([skels,merges])
        write_navis_skels_tar(self.args["out_file"], skels)
        

if __name__ == "__main__":
    mod = ReconnectModule()
    mod.run()


__all__ = [
    "ReconnectModule",
    "ReconnectParameters"
]


 
    
            