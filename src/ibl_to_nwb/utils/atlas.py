"""Utilities for working with Allen Brain Atlas and IBL atlas mappings."""

from iblatlas.regions import BrainRegions

# Cosmos acronym to full name mapping
# These are the 10 major brain divisions used in the IBL Brain-Wide Map project
# Plus 'root' which captures fiber tracts, ventricles, and other non-gray matter structures
COSMOS_FULL_NAMES = {
    "Isocortex": "Isocortex",
    "OLF": "Olfactory areas",
    "HPF": "Hippocampal formation",
    "CTXsp": "Cortical subplate",
    "CNU": "Cerebral nuclei",
    "TH": "Thalamus",
    "HY": "Hypothalamus",
    "MB": "Midbrain",
    "HB": "Hindbrain",
    "CB": "Cerebellum",
    "root": "Not in Cosmos",  # Fiber tracts, ventricles, white matter
    "void": "Outside brain",
}


def get_cosmos_color(cosmos_acronym: str, brain_regions: BrainRegions | None = None) -> tuple:
    """
    Get the RGB color for a Cosmos region.

    Parameters
    ----------
    cosmos_acronym : str
        The Cosmos region acronym (e.g., 'Isocortex', 'TH', 'root').
    brain_regions : BrainRegions, optional
        BrainRegions instance. If None, a new one will be created.

    Returns
    -------
    tuple
        RGB color as (r, g, b) with values in [0, 1].
    """
    if brain_regions is None:
        brain_regions = BrainRegions()

    try:
        index = brain_regions.acronym2index(cosmos_acronym)[1][0]
        # index may be an array if multiple matches, take first
        if hasattr(index, "__len__"):
            index = index[0]
        rgb = brain_regions.rgb[index]
        return (rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    except (IndexError, KeyError):
        return (0.5, 0.5, 0.5)  # Gray for unknown


def get_cosmos_full_name(cosmos_acronym: str) -> str:
    """
    Get the full name for a Cosmos region acronym.

    Parameters
    ----------
    cosmos_acronym : str
        The Cosmos region acronym (e.g., 'Isocortex', 'TH', 'root').

    Returns
    -------
    str
        The full name of the region.
    """
    return COSMOS_FULL_NAMES.get(cosmos_acronym, cosmos_acronym)


def get_beryl_color(beryl_acronym: str, brain_regions: BrainRegions | None = None) -> tuple:
    """
    Get the RGB color for a Beryl region.

    Parameters
    ----------
    beryl_acronym : str
        The Beryl region acronym (e.g., 'VISp', 'CA1', 'CP').
    brain_regions : BrainRegions, optional
        BrainRegions instance. If None, a new one will be created.

    Returns
    -------
    tuple
        RGB color as (r, g, b) with values in [0, 1].
    """
    if brain_regions is None:
        brain_regions = BrainRegions()

    try:
        index = brain_regions.acronym2index(beryl_acronym)[1][0]
        if hasattr(index, "__len__"):
            index = index[0]
        rgb = brain_regions.rgb[index]
        return (rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    except (IndexError, KeyError):
        return (0.5, 0.5, 0.5)


def get_beryl_full_name(beryl_acronym: str, brain_regions: BrainRegions | None = None) -> str:
    """
    Get the full name for a Beryl region acronym from the Allen atlas.

    Parameters
    ----------
    beryl_acronym : str
        The Beryl region acronym (e.g., 'VISp', 'CA1', 'CP').
    brain_regions : BrainRegions, optional
        BrainRegions instance. If None, a new one will be created.

    Returns
    -------
    str
        The full name of the region.
    """
    # Handle special cases
    if beryl_acronym == "root":
        return "Not in Beryl"
    if beryl_acronym == "void":
        return "Outside brain"

    if brain_regions is None:
        brain_regions = BrainRegions()

    try:
        index = brain_regions.acronym2index(beryl_acronym)[1][0]
        if hasattr(index, "__len__"):
            index = index[0]
        name = brain_regions.name[index]
        return str(name)
    except (IndexError, KeyError):
        return beryl_acronym


def get_ccf_acronym_at_level(
    acronym: str, target_level: int, brain_regions: BrainRegions | None = None
) -> str:
    """
    Get the ancestor acronym at a specific CCFv3 hierarchy level.

    The Allen CCFv3 atlas has 11 hierarchy levels (0-10):
    - Level 0: root
    - Level 1: grey, fiber tracts, VS
    - Level 2: CH (Cerebrum), BS (Brain stem), CB (Cerebellum)
    - Level 3: CTX, CNU, TH, HY, MB, P, MY, CBX, CBN
    - ...
    - Level 10: Most specific regions (e.g., VISp2/3)

    Parameters
    ----------
    acronym : str
        The brain region acronym (e.g., 'SSp-ll2/3', 'VISp', 'CA1').
    target_level : int
        The target hierarchy level (0-10). If the region is already at or
        above this level, returns the region itself.
    brain_regions : BrainRegions, optional
        BrainRegions instance. If None, a new one will be created.

    Returns
    -------
    str
        The acronym of the ancestor at the target level.
    """
    # Handle special cases
    if acronym in ("root", "void"):
        return acronym

    if brain_regions is None:
        brain_regions = BrainRegions()

    try:
        index = brain_regions.acronym2index(acronym)[1][0]
        if hasattr(index, "__len__"):
            index = index[0]

        current_level = brain_regions.level[index]

        # If already at or above target level, return as is
        if current_level <= target_level:
            return acronym

        # Walk up the hierarchy until we reach target level
        current_idx = index
        for _ in range(20):  # Safety limit
            parent_id = brain_regions.parent[current_idx]
            if parent_id == 0 or parent_id == 997:  # root
                return "root"

            parent_idx = brain_regions.id2index(int(parent_id))[1][0]
            if hasattr(parent_idx, "__len__"):
                parent_idx = parent_idx[0]

            parent_level = brain_regions.level[parent_idx]
            if parent_level <= target_level:
                return str(brain_regions.acronym[parent_idx])

            current_idx = parent_idx

        return acronym  # Fallback
    except (IndexError, KeyError):
        return acronym


def get_ccf_color(acronym: str, brain_regions: BrainRegions | None = None) -> tuple:
    """
    Get the RGB color for a CCFv3 region.

    Parameters
    ----------
    acronym : str
        The brain region acronym (e.g., 'VISp', 'CA1', 'CP').
    brain_regions : BrainRegions, optional
        BrainRegions instance. If None, a new one will be created.

    Returns
    -------
    tuple
        RGB color as (r, g, b) with values in [0, 1].
    """
    if brain_regions is None:
        brain_regions = BrainRegions()

    try:
        index = brain_regions.acronym2index(acronym)[1][0]
        if hasattr(index, "__len__"):
            index = index[0]
        rgb = brain_regions.rgb[index]
        return (rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    except (IndexError, KeyError):
        return (0.5, 0.5, 0.5)


def get_ccf_full_name(acronym: str, brain_regions: BrainRegions | None = None) -> str:
    """
    Get the full name for a CCFv3 region acronym from the Allen atlas.

    Parameters
    ----------
    acronym : str
        The brain region acronym (e.g., 'VISp', 'CA1', 'CP').
    brain_regions : BrainRegions, optional
        BrainRegions instance. If None, a new one will be created.

    Returns
    -------
    str
        The full name of the region.
    """
    # Handle special cases
    if acronym == "root":
        return "root"
    if acronym == "void":
        return "Outside brain"

    if brain_regions is None:
        brain_regions = BrainRegions()

    try:
        index = brain_regions.acronym2index(acronym)[1][0]
        if hasattr(index, "__len__"):
            index = index[0]
        name = brain_regions.name[index]
        return str(name)
    except (IndexError, KeyError):
        return acronym
