import argschema
import os
import subprocess
from pathlib import Path


# Helper function to run awscli sync command
def run_aws_sync(source, destination):
    subprocess.run([
        "aws",
        "s3",
        "sync",
        str(source),
        str(destination),
        "--storage-class", "INTELLIGENT_TIERING",
        "--exact-timestamps",  # to avoid unnecessary copies
    ], check=True)


# Helper function to run awscli cp command for single files
def run_aws_cp(source, destination):
    subprocess.run([
        "aws",
        "s3",
        "cp",
        str(source),
        str(destination),
        "--storage-class", "INTELLIGENT_TIERING",
    ], check=True)


def copy_og(base_dir, s3_base, aws_key, aws_sec_key, region='us-west-2', workers=20):

    env = os.environ.copy()
    env["AWS_MAX_CONCURRENT_REQUESTS"] = str(workers)

    # Set environment variables for AWS credentials and region
    if aws_key is not None:
        os.environ["AWS_ACCESS_KEY_ID"] = aws_key
    if aws_sec_key is not None:
        os.environ["AWS_SECRET_ACCESS_KEY"] = aws_sec_key

    os.environ["AWS_DEFAULT_REGION"] = region

    base_dir = Path(base_dir)
    s3_base = s3_base.rstrip('/') + '/'

    paths = []
    # Limit search depth to 3 levels: base_dir / * / * / *
    for level1 in base_dir.iterdir():
        if level1.is_dir():
            for level2 in level1.iterdir():
                if level2.is_dir():
                    for level3 in level2.iterdir():
                        if level3.is_file() and level3.name in [".zarray", ".zgroup", "zarr.json"]:
                            paths.append(level3.resolve())
                elif level2.is_file() and level2.name in [".zarray", ".zgroup", "zarr.json"]:
                    paths.append(level2.resolve())
        elif level1.is_file() and level1.name in [".zarray", ".zgroup", "zarr.json"]:
            paths.append(level1.resolve())

    # Copy individual files first
    for path in paths:
        print(path)
        relative_path = path.relative_to(base_dir)
        s3_path = f"{s3_base}{relative_path.parent}/"
        
        if "./" in s3_path:
            run_aws_cp(path, s3_base)   
        else:
            run_aws_cp(path, s3_path)

    # Then sync the full folder contents (recursive)
    #print(f"Syncing full directory {base_dir} to {s3_base}")
    run_aws_sync(base_dir, s3_base)
    
    
    
def copy(base_dir, s3_base, aws_key, aws_sec_key, region='us-west-2', workers=20):

    env = os.environ.copy()
    env["AWS_MAX_CONCURRENT_REQUESTS"] = str(workers)

    # Set environment variables for AWS credentials and region
    if aws_key is not None:
        os.environ["AWS_ACCESS_KEY_ID"] = aws_key
    if aws_sec_key is not None:
        os.environ["AWS_SECRET_ACCESS_KEY"] = aws_sec_key

    os.environ["AWS_DEFAULT_REGION"] = region

    base_dir = Path(base_dir)
    s3_base = s3_base.rstrip('/') + '/'

    paths = []
    # Limit search depth to 3 levels: base_dir / * / * / *
    for level in ['*','*/*','*/*/*']:
        for path in base_dir.glob(level):
                if path.is_file() and path.name in [".zarray", ".zgroup", "zarr.json"]:
                    paths.append(path.resolve())
                
    print(paths)
    # Copy individual files first
    for path in paths:
        print(path)
        relative_path = path.relative_to(base_dir)
        s3_path = f"{s3_base}{relative_path.parent}/"
        
        if "./" in s3_path:
            run_aws_cp(path, s3_base)   
        else:
            run_aws_cp(path, s3_path)
            
    for level in ['*','*/*','*/*/*']:
        for path in base_dir.glob(level):
            if (
            path.is_dir()
            and path.name == '5'
            and len(path.relative_to(base_dir).parts) <= 3):
                print(f"Found folder named '5', uploading: {path.resolve()}")
                s3_path = f"{s3_base}{path.relative_to(base_dir)}/"
                run_aws_sync(path, s3_path)
                break  # Stop after uploading the first match
                

    # Then sync the full folder contents (recursive)
    print(f"Syncing full directory {base_dir} to {s3_base}")
    run_aws_sync(base_dir, s3_base)





class CopyParameters(argschema.ArgSchema):
    input_path = argschema.fields.String(required=True)
    output_path = argschema.fields.String(required=True)
    AWS_key = argschema.fields.String(required=False, default=None, allow_none=True)
    AWS_sec_key = argschema.fields.String(required=False, default=None, allow_none=True)
    region = argschema.fields.String(required=False, default='us-west-2')


class CopyModule(argschema.ArgSchemaParser):
    default_schema = CopyParameters

    def run(self):
        for key, value in self.args.items():
            if value == 'None':
                self.args[key] = None

        copy(self.args['input_path'], self.args['output_path'],
             self.args['AWS_key'], self.args['AWS_sec_key'],
             region=self.args['region'])


if __name__ == "__main__":
    mod = CopyModule()
    mod.run()

__all__ = [
    "CopyModule",
    "CopyParameters"
]



