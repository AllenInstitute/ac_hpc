# ac_hpc

<!-- brainlife-app:begin (generated from the App manifest; edit the manifest, not this block) -->

> **Submits a Nextflow job on a SLURM cluster to deskew a TIFF light-sheet image and write it as a Zarr v3 volume, as part of the Allen Institute axonal connectomics pipeline.**

Reads the method and output directory from config.json and calls submit_job.py, which writes a Nextflow run script for the deskew_tiff step of the axonal connectomics segmentation/skeletonisation pipeline and submits it with sbatch. It is designed for the Allen Institute HPC environment (sbatch, Nextflow, local Java) and returns as soon as the job is submitted, so the Zarr output is written to deskew_out_dir by the cluster job rather than to the App's working directory.

| | |
|---|---|
| 📥 **Inputs** | `tif` |
| 📤 **Outputs** | `zarr v3` |
| ⚙️ **Resources** | 2 GB memory · 0.08 h walltime |
| 🔗 **Run it** | [doi.org/10.25663/brainlife.app.872](https://doi.org/10.25663/brainlife.app.872) |

#### 📥 Inputs

| Input | Datatype | Required | Description |
|---|---|---|---|
| `single_file` | `tif` | yes | Single TIFF image stack to deskew. main reads the config key 'single_file', while this input provides 'tif'. |

#### 📤 Outputs

| Output | Datatype | Description |
|---|---|---|
| `deskew_out_dir` | `zarr v3` | Intended deskewed Zarr v3 volume; it is written by the submitted cluster job to deskew_out_dir, not to the App working directory. |

<details>
<summary><b>⚙️ Parameters</b> (2)</summary>

| Parameter | Type | Default | Description |
|---|---|---|---|
| `method` | string | `deskew_tiff` | Pipeline step passed to submit_job.py (deskew_tiff for TIFF to deskewed Zarr). |
| `deskew_out_dir` | string |  | Directory where the deskewed Zarr output is written by the cluster job (required by the deskew_tiff step). |

</details>

<!-- brainlife-app:end -->

This is a repository for all hpc processing files related to the axonal connectomics segmentation/skeletonization pipeline.
