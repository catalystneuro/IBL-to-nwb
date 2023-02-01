from abc import ABC
from pathlib import Path

import yaml
from pynwb import NWBHDF5IO

from .alyx_to_nwb_converter import Alyx2NWBConverter
from .alyx_to_nwb_metadata import Alyx2NWBMetadata


class Alyx2NWBGuiConverter(Alyx2NWBConverter, ABC):
    def __init__(self, source_path, nwbfile, metadata):
        with open(source_path, "r") as f:
            source_path_dict = yaml.safe_load(f)
        source_path_dict.update(metadata)
        super(Alyx2NWBGuiConverter, self).__init__(saveloc=nwbfile, nwb_metadata_file=source_path_dict)

    def save(self, saveloc):
        print("Saving to file, please wait...")
        with NWBHDF5IO(saveloc, "w") as io:
            io.write(self.nwbfile)
            print("File successfully saved at: ", str(saveloc))


class Alyx2NWBGui(Alyx2NWBMetadata, ABC):
    def __init__(self, eid=None, one_obj=None, metadata_fileloc=None, nwbfile_saveloc=None, **one_search_kawargs):
        """
        Use a GUI to overwrite the metadata created by Alyx2NWBMetadata
        Parameters
        ----------
        eid: str
            Mice experiment id as uuid
        one_obj: ONE()
            an ONE instance after user authentication
        metadata_fileloc: str
            filepath of the metadata file in yaml/json format. Use this if eid/one_obj is none.
        nwbfile_saveloc: str
            default nwbfile path/name.nwb to save to.
        one_search_kwargs: dict
            search terms supported by the ONE api to retrieve an eid of interest.
        """
        try:
            from nwb_conversion_tools.gui.nwb_conversion_gui import nwb_conversion_gui
        except:
            raise Exception(
                "installation required: "
                "'pip install git+https://github.com/catalystneuro/nwb-conversion-tools.git"
                "@fb9703f8e86072f04356883975e5dfffa773913e#egg=nwb-conversion-tools'"
            )
        super(Alyx2NWBGui, self).__init__(eid=eid, one_obj=one_obj, **one_search_kawargs)

        self.metadata = dict()
        self.metadata.update(self.nwbfile_metadata)
        self.metadata.update(dict(Subject=self.subject_metadata["IBLSubject"]))
        if metadata_fileloc is None:
            self.complete_metadata_fileloc = Path.cwd() / "ibl_metadata_file.yaml"
        elif Path(metadata_fileloc).suffix != ".yaml":
            self.complete_metadata_fileloc = str(Path(metadata_fileloc).with_suffix(".yaml"))
        else:
            self.complete_metadata_fileloc = metadata_fileloc
        self.nwbfile_saveloc = nwbfile_saveloc
        self.write_metadata(self.complete_metadata_fileloc, savetype=".yaml")
        source_paths = dict(ibl_metadata_filepath=dict(type="file", path=self.complete_metadata_fileloc))
        self.temp_metadata_file = Path.cwd() / "tempfile.yaml"
        with open(self.temp_metadata_file, "w") as f:
            yaml.safe_dump(self.metadata, f)
        nwb_conversion_gui(
            metafile=self.temp_metadata_file,
            conversion_class=Alyx2NWBGuiConverter,
            source_paths=source_paths,
            kwargs_fields={},
            nwbfile_loc=self.nwbfile_saveloc,
            load_nwbwidgets=False,
        )
