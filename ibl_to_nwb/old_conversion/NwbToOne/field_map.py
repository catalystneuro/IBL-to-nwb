import json


def _str(obj):
    return str(obj) if obj is not None else None


field_map_nwbfile = {
    "session_start_time": {"name": "start_time", "dtype": _str},
    "experiment_description": {"name": "project", "dtype": _str},
    "experimenter": {"name": "users", "dtype": list},
    "lab": {"name": "lab", "dtype": _str},
    "protocol": {"name": "task_protocol", "dtype": _str},
    "session_description": {"name": "procedures", "dtype": lambda x: [_str(x)]},
}

field_map_session_data = {
    "location": {"name": "location", "dtype": _str},
    "project": {"name": "project", "dtype": _str},
    "type": {"name": "type", "dtype": _str},
    "number": {"name": "number", "dtype": lambda x: int(x.item()) if "numpy" in str(type(x)) else int(x)},
    "end_time": {"name": "end_time", "dtype": _str},
    "parent_session": {"name": "parent_session", "dtype": _str},
    "url": {"name": "url", "dtype": _str},
    "qc": {"name": "qc", "dtype": _str},
    "extended_qc": {"name": "extended_qc", "dtype": json.loads},
    "wateradmin_session_related": {"name": "wateradmin_session_related", "dtype": json.loads},
    "notes": {"name": "notes", "dtype": json.loads},
    "json": {"name": "json", "dtype": json.loads},
}
session_data_unknown_fields = ["narrative"]
session_data_other_fields = ["subject", "n_trials", "n_correct_trials", "probe_insertion"]

field_map_subject = {
    "subject_id": {"name": "id", "dtype": _str},
    "description": {"name": "description", "dtype": _str},
    "genotype": {"name": "genotype", "dtype": lambda x: [_str(x)]},
    "sex": {"name": "sex", "dtype": _str},
    "species": {"name": "species", "dtype": _str},
    "weight": {"name": "reference_weight", "dtype": lambda x: float(x.item()) if "numpy" in str(type(x)) else float(x)},
    "date_of_birth": {"name": "birth_date", "dtype": _str},
    "age": {"name": "age_weeks", "dtype": lambda x: int(x.strip("PW"))},
}

field_map_IBL_subject = {
    "nickname": {"name": "nickname", "dtype": _str},
    "url": {"name": "url", "dtype": _str},
    "responsible_user": {"name": "responsible_user", "dtype": _str},
    "death_date": {"name": "death_date", "dtype": _str},
    "litter": {"name": "litter", "dtype": _str},
    "strain": {"name": "strain", "dtype": _str},
    "source": {"name": "source", "dtype": _str},
    "line": {"name": "line", "dtype": _str},
    "projects": {"name": "projects", "dtype": _str},
    "session_projects": {"name": "session_projects", "dtype": _str},
    "lab": {"name": "lab", "dtype": _str},
    "alive": {"name": "alive", "dtype": bool},
    "last_water_restriction": {"name": "last_water_restriction", "dtype": _str},
    "expected_water": {
        "name": "expected_water",
        "dtype": lambda x: float(x.item()) if "numpy" in str(type(x)) else float(x),
    },
    "remaining_water": {
        "name": "remaining_water",
        "dtype": lambda x: float(x.item()) if "numpy" in str(type(x)) else float(x),
    },
    "weighings": {"name": "weighings", "dtype": json.loads},
    "water_administrations": {"name": "water_administrations", "dtype": json.loads},
}

field_map_probes = {
    "name": {"name": "name", "dtype": _str},
    "id": {"name": "id", "dtype": _str},
    "model": {"name": "model", "dtype": _str},
    "trajectory_estimate": {"name": "trajectory_estimate", "dtype": json.loads},
}
