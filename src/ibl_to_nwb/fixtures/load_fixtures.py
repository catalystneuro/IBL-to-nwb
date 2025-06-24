from pathlib import Path

import pandas as pd


def load_bwm_df():
    path = Path(__file__).parent / "bwm_df.pqt"
    return pd.read_parquet(path)


def load_bwm_units_df():
    path = Path(__file__).parent / "bwm_units_df.pqt"
    return pd.read_parquet(path)
