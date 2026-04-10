# Reproducing the Conversion Environment

This repository tracks three dependency lock files so that the exact environment
used to produce the BWM NWB files on DANDI can be reproduced. All three are
generated from `pyproject.toml` and committed to version control.

## Reproducing with uv (recommended)

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run:

```bash
uv sync
```

This reads `uv.lock` and installs the exact same package versions, including
git-sourced dependencies pinned to specific commits. It works on Linux, macOS,
and Windows because `uv.lock` encodes a universal resolution: it captures the
dependency graph for all platforms and Python versions in a single file. uv
achieves this without running on every OS because it reads package metadata from
PyPI, which already declares platform-conditional dependencies, and walks all
branches hypothetically.

## Reproducing with pip or other tools

If you do not use uv, install from the PEP 751 standard lock file:

```bash
pip install -r pylock.toml
```

`pylock.toml` (PEP 751, accepted March 2025) is a flat, resolved manifest for a
single target environment. Unlike `uv.lock`, it does not encode cross-platform
branching logic. PEP 751 made this trade-off intentionally: any installer can
read the file directly without needing its own resolver. The trade-off is that
the file represents one platform snapshot. If your platform differs from the one
used to export it, some packages may not match.

pip 25.1+ supports installing from `pylock.toml`, though there is a
[known bug](https://github.com/pypa/pip/issues/13864) as of early 2026. If pip
fails, you can use `uv pip install -r pylock.toml` as a fallback. pdm and pipenv
also support the format.

## Reproducing with conda

If you prefer conda, create the environment from `environment.yml`:

```bash
conda env create -f environment.yml
conda activate ibl-to-nwb
```

Conda differs from pip/uv in that it manages both Python packages and the compiled
C libraries they depend on (HDF5, BLAS, etc.). When conda installs `h5py`, it also
installs the specific `hdf5` C library it was built against. pip/uv instead ship
pre-built wheels that link against whatever system libraries are already present.
This makes conda environments more self-contained but also heavier and slower to
resolve.

About half of the direct dependencies are available on conda-forge. The rest
(IBL-specific packages, NWB extensions, neuroconv) are installed via pip inside
the conda environment. Because of this mixed installation, the conda path is less
tightly pinned than `uv.lock` or `pylock.toml`. It will give you a working
environment but not necessarily the exact same versions used during the conversion.

## Human-readable reference

`requirements_freeze.txt` is a `pip freeze` snapshot of the environment that was
used to run the conversions. It is the simplest way to inspect what was installed
(package names and versions, one per line) but it does not include hashes and is
specific to one platform. It is not intended for installation, just for reference.

## How the three files differ

| File | Tool needed | Cross-platform | Hashes | Git commit pins | Pins C libraries |
|---|---|---|---|---|---|
| `uv.lock` | uv | Yes (universal) | Yes | Yes | No |
| `pylock.toml` | Any PEP 751 tool | No (single platform) | Yes | Yes | No |
| `environment.yml` | conda | No (single platform) | No | No | Yes (via conda-forge) |
| `requirements_freeze.txt` | Human eyes | No | No | Yes (as URL fragments) | No |

## Notes on dependency overrides

A few packages are installed from git rather than PyPI because unreleased changes
are needed. These are declared in `[tool.uv.sources]` in `pyproject.toml`, each
with a comment explaining why and when the git source can be dropped. All three
lock files record the exact commit hash for these packages.

The `[tool.uv]` section also forces `hdmf>=5.0` past the upper bound that `pynwb`
declares on PyPI (`hdmf<5`). This is necessary because hdmf 5.0 includes
performance improvements for large ephys writes. This override only takes effect
with uv. See the comments in `pyproject.toml` for details.

## Regenerating the lock files

After changing `pyproject.toml`, regenerate all three:

```bash
uv lock                                          # uv.lock
uv export --format pylock.toml -o pylock.toml    # pylock.toml (PEP 751)
uv pip freeze > requirements_freeze.txt          # pip freeze snapshot
```
