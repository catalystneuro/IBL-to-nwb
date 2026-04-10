# Witten ibl_witten_13 Trouble Session (Phase 3A)

## Session

One session from subject ibl_witten_13 (wittenlab) fails raw conversion due to
a missing `firstSample` field in its SpikeGLX `.meta` files.

| EID | Date | Probe | SpikeGLX version |
|-----|------|-------|-----------------|
| `ebe090af-5922-4fcd-8fc6-17b8ba7bad6d` | 2019-12-03 | probe01 | `appVersion=20190413` (Phase 3A, Imec API v4.3) |

This is a standard Neuropixels 1.0 session (384 channels, native AP + LF
bands, two probes). The binary data is correct.

## Problem: Missing `firstSample`

This session was recorded with an early SpikeGLX build (Phase 3A, April 2019).
The `.meta` files lack the `firstSample` field entirely.

**How it breaks:** Neo's `spikeglxrawio.py` unconditionally reads
`info["meta"]["firstSample"]` (line 277):

```
KeyError: 'firstSample'
```

SpikeGLX's own C++ code (`DataFile::firstCt()`) defaults to 0 when the field
is absent. Old recordings without this field are always single-file (multi-disk
splitting was only added in 2020), so the first sample is always 0.

**Fix:** Append `firstSample=0` to meta files that lack the field.

## Implementation

### Patch module

- `src/ibl_to_nwb/conversion/spikeglx_first_sample_patch.py`: injects
  `firstSample=0` into meta files missing the field (idempotent)

### Where the patch is applied

Same two sites as the Steinmetz patches:

1. **Decompressed ephys folder** (`session.py`, around line 275): patches
   files before neo's reader uses them for raw conversion
2. **On-the-fly in electrode table creation** (`electrodes.py`, around
   line 577): patches before probeinterface reads, covering both raw and
   processed paths

### Upstream fix

**python-neo:** Use `.get("firstSample", 0)` instead of direct key access in
`spikeglxrawio.py` line 277. This would handle all old Phase 3A recordings
without needing external patches.
