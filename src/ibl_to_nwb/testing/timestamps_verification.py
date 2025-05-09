# %%
import numpy as np
from pathlib import Path
from one.api import ONE
from brainbox.io.one import SpikeSortingLoader
# from deploy.iblsdsc import OneSdsc as ONE

eid = "caa5dddc-9290-4e27-9f5e-575ba3598614"

one_kwargs = dict(
        cache_dir=Path.home() / "ibl_scratch" / "ibl_conversion" / eid / "cache",
        mode='local'
    )
one = ONE(**one_kwargs)

sl = SpikeSortingLoader(one=one, eid=eid, pname="probe00")

print(sl.samples2times(np.arange(0, 10), direction="forward", band='lf'))
# %%
