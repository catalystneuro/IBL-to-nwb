import os
import yaml
from abc import ABC

from .alyx_to_nwb_converter import Alyx2NWBConverter
from .alyx_to_nwb_metadata import Alyx2NWBMetadata


class Alyx2NWBGuiConverter(Alyx2NWBConverter, ABC):

    def __init__(self, source_path, nwbfile, metadata):
        with open(source_path, 'r') as f:
            source_path_dict = yaml.safe_load(f)
        source_path_dict.update(metadata)
        super(Alyx2NWBGuiConverter, self).__init__(saveloc=nwbfile, nwb_metadata_file=source_path_dict)


class Alyx2NWBGui(Alyx2NWBMetadata, ABC):

    def __init__(self, eid=None, one_obj=None, metadata_fileloc=None,
                 nwbfile_saveloc=None, **one_search_kawargs):
        from nwb_conversion_tools.gui.nwb_conversion_gui import nwb_conversion_gui
        super(Alyx2NWBGui, self).__init__(eid=eid, one_obj=one_obj, **one_search_kawargs)

        self.metadata = dict()
        self.metadata.update(self.nwbfile_metadata)
        self.metadata.update(self.subject_metadata)
        if metadata_fileloc is None:
            self.metadata_fileloc = os.path.join(os.getcwd(), 'ibl_metadata_file.json')
        else:
            self.metadata_fileloc = metadata_fileloc
        self.nwbfile_saveloc = nwbfile_saveloc
        metedata_complete = self.write_metadata(self.metadata_fileloc, savetype='yaml')
        source_paths = dict(ibl_metadata_filepath=dict(type='file', path=metedata_complete))
        self.metadata_file = os.path.join(os.path.dirname(self.metadata_fileloc), f'temp_nwbmetadatasave_{self.eid[-4:]}.yaml')
        with open(self.metadata_file, 'w') as f:
            yaml.safe_dump(self.metadata, f)
        nwb_conversion_gui(
            metafile=self.metadata_file,
            conversion_class=Alyx2NWBGuiConverter,
            source_paths=source_paths,
            nwbfile_loc=self.nwbfile_saveloc,
            load_nwbwidgets=False
        )
