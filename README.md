<h1 align="center">Convert_Tiff_to_Zarr3</h1>

<p align="center">
  Submits a Nextflow job on a SLURM cluster to deskew a TIFF light-sheet image and write it as a Zarr v3 volume, as part of the Allen Institute axonal connectomics pipeline.
</p>

<p align="center">
  <a href="https://github.com/brainlife/abcd-spec"><img src="https://img.shields.io/badge/ABCD_Spec-v1.1-green.svg" alt="ABCD Spec v1.1"></a>
  <a href="https://doi.org/10.25663/brainlife.app.872"><img src="https://img.shields.io/badge/Brainlife-brainlife.app.872-blue.svg" alt="Run on brainlife.io"></a>
</p>

## At a glance

<!-- brainlife-app:begin (generated from the App manifest; edit the manifest, not this block) -->

> **Submits a Nextflow job on a SLURM cluster to deskew a TIFF light-sheet image and write it as a Zarr v3 volume, as part of the Allen Institute axonal connectomics pipeline.**

Reads the method and output directory from config.json and calls submit_job.py, which writes a Nextflow run script for the deskew_tiff step of the axonal connectomics segmentation/skeletonisation pipeline and submits it with sbatch. It is designed for the Allen Institute HPC environment (sbatch, Nextflow, local Java) and returns as soon as the job is submitted, so the Zarr output is written to deskew_out_dir by the cluster job rather than to the App's working directory.

| | |
|---|---|
| **Inputs** | `tif` |
| **Outputs** | `zarr v3` |
| **Resources** | 2 GB memory · 0.08 h walltime |
| **Run it** | [doi.org/10.25663/brainlife.app.872](https://doi.org/10.25663/brainlife.app.872) |

#### Inputs

| Input | Datatype | Required | Description |
|---|---|---|---|
| `single_file` | `tif` | yes | Single TIFF image stack to deskew. main reads the config key 'single_file', while this input provides 'tif'. |

#### Outputs

| Output | Datatype | Description |
|---|---|---|
| `deskew_out_dir` | `zarr v3` | Intended deskewed Zarr v3 volume; it is written by the submitted cluster job to deskew_out_dir, not to the App working directory. |

<details>
<summary><b>Parameters</b> (2)</summary>

| Parameter | Type | Default | Description |
|---|---|---|---|
| `method` | string | `deskew_tiff` | Pipeline step passed to submit_job.py (deskew_tiff for TIFF to deskewed Zarr). |
| `deskew_out_dir` | string |  | Directory where the deskewed Zarr output is written by the cluster job (required by the deskew_tiff step). |

</details>

<!-- brainlife-app:end -->

## Running the App

### On brainlife.io

Open the App at [doi.org/10.25663/brainlife.app.872](https://doi.org/10.25663/brainlife.app.872), choose `tif` from your project, set the parameters and press **Execute**. The results are saved to your project as `zarr v3`.

### Locally

You need [`jq`](https://jqlang.github.io/jq/).

1. Clone this repository.
2. Create `config.json` with the paths to your inputs and the parameters:

   ```json
   {
       "tif": "/path/to/single_file/tif",
       "method": "deskew_tiff",
       "deskew_out_dir": ""
   }
   ```

3. Run `./main`.

## Citing

If you use this App, please cite it, the software it builds on and brainlife.io:

- Convert_Tiff_to_Zarr3. brainlife.io App. [doi:10.25663/brainlife.app.872](https://doi.org/10.25663/brainlife.app.872)
- Hayashi S, Caron BA, Heinsfeld AS, et al. brainlife.io: a decentralized and open-source cloud platform to support neuroscience research. *Nature Methods* 21:809–813 (2024). [doi:10.1038/s41592-024-02237-2](https://doi.org/10.1038/s41592-024-02237-2)
- Avesani P, McPherson B, Hayashi S, et al. The open diffusion data derivatives, brain data upcycling via integrated publishing of derivatives and reproducible open cloud services. *Scientific Data* 6:69 (2019). [doi:10.1038/s41597-019-0073-y](https://doi.org/10.1038/s41597-019-0073-y)

## Authors

Maintained by [@AllenInstitute](https://github.com/AllenInstitute).
