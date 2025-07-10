from pathlib import Path
import json
import pandas as pd


def load_bwm_df():
    path = Path(__file__).parent / "bwm_df.pqt"
    return pd.read_parquet(path)


def load_bwm_units_df():
    path = Path(__file__).parent / "bwm_units_df.pqt"
    return pd.read_parquet(path)


def load_bwm_qc():
    path = Path(__file__).parent / "bwm_qc.json"
    with open(path, "r") as fH:
        return json.load(fH)
