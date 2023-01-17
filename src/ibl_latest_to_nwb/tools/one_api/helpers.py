from one.api import ONE


def session_to_probe_id_mapping(one: ONE):
    """
    Helper function to retrieve the unique probe identifiers for sessions that have probes.
    Parameters
    ----------
    one: ONE
        ONE API client that connects to the Alyx database.

    Returns
    -------
    The dictionary with session identifiers mapped to probe identifiers.
    """
    # get an iterable with all probe identifiers
    probe_insertions = one.alyx.rest("insertions", "list")

    session_to_probe_id = dict()
    for probe_entry in probe_insertions:
        # sessions can have multiple probe insertions
        if probe_entry["session"] in session_to_probe_id:
            session_to_probe_id[probe_entry["session"]].append(probe_entry["id"])
        else:
            session_to_probe_id[probe_entry["session"]] = [probe_entry["id"]]

    return session_to_probe_id


def get_num_probes(one: ONE, probe_id: str):
    query_str = "*probe*ap.cbin"
    session_id, _ = one.pid2eid(pid=probe_id)

    num_probes = len(one.list_datasets(session_id, query_str))
    return num_probes
