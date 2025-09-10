# from one.api import ONE
# from brainbox.io.one import SessionLoader

# one = ONE()
# eid = "41431f53-69fd-4e3b-80ce-ea62e03bf9c7"
# REVISION = "2025-05-06"
# session_loader = SessionLoader(eid=eid, one=one, revision=REVISION)
# session_loader.load_pose(tracker="dlc")

# %%
from one.api import ONE
# one = ONE()
from deploy.iblsdsc import OneSdsc as ONE
eid = "dc21e80d-97d7-44ca-a729-a8e3f9b14305"

# %% load_object leads to an inconsistent state because 
one.load_object(eid, "_ibl_rightCamera", revision="2025-05-06")
"""
/home/georg/code/ONE/one/util.py:428: ALFWarning: Multiple revisions: "", "2023-04-20"
  warnings.warn(f'Multiple revisions: {rev_list}', alferr.ALFWarning)
Inconsistent dimensions for object: rightCamera 
(965580, 33),	dlc
(897783, 2),	features
(965580, 69),	lightningPose
(965580,),	times
"""

# %%
# this is because alf/_ibl_rightCamera.features.pqt is of shape (897783, 2)
one.load_dataset(eid, "alf/_ibl_rightCamera.features.pqt").shape # = (897783, 2)

# whereas only the next revision of this dataset has a matching shape
one.load_dataset(eid, "alf/#2025-06-04#/_ibl_rightCamera.features.pqt").shape # = (965580, 2)

# just to verify the default
one.load_dataset(eid, "_ibl_rightCamera.times", revision='2023-04-20').shape # = (965580,)