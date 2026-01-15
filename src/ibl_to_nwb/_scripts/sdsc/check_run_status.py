# %%
import os
import shutil
from pathlib import Path

from pynwb import NWBHDF5IO

from ibl_to_nwb import bwm_to_nwb
from ibl_to_nwb.fixtures import load_fixtures
from ibl_to_nwb.testing import check_nwbfile_for_consistency
# Set the filter to show each warning only once for a specific module

# if running on SDSC, use the OneSdsc, else normal
from deploy.iblsdsc import OneSdsc as ONE
import warnings

warnings.filterwarnings("once", category=UserWarning, module="ONE")

base_path = Path("/mnt/sdceph/users/ibl/data/quarantine/BWM_to_NWB/")

# %%
states = ['running','todo','done']
eids = {}
for state in states:
    eids[state] = set([path.name for path in (base_path / f"eids_{state}").glob('*')])
    print(state, len(eids[state]))

# %%
bwm_df = load_fixtures.load_bwm_df()
eids['bwm'] = set(bwm_df['eid'].unique())

# %% present files
import re
pattern = r'.*ses-(.+)_desc.*'
nwbfiles = list(base_path.rglob('*.nwb'))
eids['converted'] = []
for nwbfile in nwbfiles:
    match = re.search(pattern, nwbfile.name)
    eid = match.group(1)
    eids['converted'].append(eid)

# %%
len(set(eids['converted']))

# %%
len(eids['running'].union(eids['todo']).union(eids['done']))

# %% errored
eids['err'] = [path.name.split('_')[0] for path in base_path.glob('*_err.log')]

# %% resubmit
# make sure to first keep error logs
for eid in eids['err']:
    (base_path / 'eids_todo' / eid).touch()

# %% remove all debug files
for nwbfile in nwbfiles:
    if 'debug' in nwbfile.name:
        os.remove(nwbfile)

# %%
import re

text = "Here is a code: 123-456-7890 and some text."
pattern = r'[\d-]+'  # Matches sequences of digits and hyphens

# To find the first occurrence
match = re.search(pattern, text)
if match:
    extracted_substring = match.group()
    print("Extracted substring:", extracted_substring)

# To find all occurrences
matches = re.findall(pattern, text)
print("All extracted substrings:", matches)