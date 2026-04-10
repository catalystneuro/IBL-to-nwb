# Neuropixels 2.0 Conversion

This section covers the conversion of IBL sessions recorded with Neuropixels 2.0
(NP2.4) probes. The only structural difference from the Brain Wide Map (NP1.0)
conversion is the raw ephys data: NP2.4 probes have 4 physically separated shanks
per probe, and the IBL recording team stored each shank as a separate compressed
file (`probe00a/`, `probe00b/`, etc.). Everything else (trials, wheel, licks, pose
estimation, passive task, motion energy, spike sorting) follows the standard IBL
ALF format and uses the same `convert_session()` pipeline.

Because the per-shank file organization and modified `.meta` files are specific to
this IBL dataset, the standard SpikeGLX readers (Neo, SpikeInterface) cannot parse
the data directly. A dedicated `IblNeuropixels2Converter` with custom extractor and
interface classes handles the per-shank decompression, metadata parsing, and probe
geometry extraction. This converter is less robust than the standard pipeline
because it relies on project-specific loading logic rather than the well-maintained
SpikeInterface/Neo path. If future NP2 sessions follow the standard SpikeGLX file
layout (all shanks in a single file), they would use the regular pipeline instead.

## Notebook walkthrough

See the [neuropixels_2.ipynb notebook](https://github.com/catalystneuro/IBL-to-nwb/blob/main/notebooks/neuropixels_2.ipynb)
for a complete walkthrough including electrode geometry visualization and processed
behavioral data inspection.

## Running the conversion

The raw ephys conversion uses a standalone script because the NP2 data must be
pre-downloaded (it is not yet available on openalyx):

```bash
uv run python src/ibl_to_nwb/_scripts/convert_neuropixels2_to_nwb.py
```

The script is configured for the KM_038 session (steinmetzlab, 2025-05-19) with
3 NP2.4 probes (12 shanks total). Edit `TARGET_EID` and `session_folder` in the
script to convert a different session.

For processed/behavioral data, use `convert_single_bwm_to_nwb.py` once the session
is registered on openalyx.

## Current caveats

- **Data not yet on openalyx.** The session was shared directly by the experimenters.
  Raw conversion uses a standalone script; processed data requires a temporary
  workaround script.
- **No anatomical localization.** Histology has not been processed, so electrode
  coordinates are probe-relative only (no Allen CCF brain region assignments).
- **No spike sorting in the NWB yet.** Sorted spike data exists in the source ALF
  files but has not been integrated. Once on openalyx, `IblSortingInterface` will
  handle this automatically.
