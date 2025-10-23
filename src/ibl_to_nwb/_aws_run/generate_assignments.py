"""Generate shard assignment files for distributed IBL conversion.

This script divides the full list of session EIDs from bwm_df into N equal parts
and saves each part as a JSON file. These files will be downloaded by EC2 instances.

Usage:
    python generate_assignments.py --num-shards 50 --output-dir ./assignments
    python generate_assignments.py --num-shards 3 --output-dir ./assignments --stub-test
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from ibl_to_nwb.fixtures import load_fixtures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate shard assignment files for distributed conversion"
    )
    parser.add_argument(
        "--num-shards",
        type=int,
        required=True,
        help="Number of shards (should match number of EC2 instances)",
    )
    parser.add_argument(
        "--stub-test",
        action="store_true",
        help="Generate small test assignments (first 10 sessions only)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Setup logging with DEBUG level (hardcoded for max verbosity)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)s: %(message)s",
    )
    logger = logging.getLogger(__name__)

    # Hardcoded output directory
    OUTPUT_DIR = Path(__file__).parent / "assignments"

    logger.info("=" * 80)
    logger.info("GENERATING SHARD ASSIGNMENTS")
    logger.info("=" * 80)

    # Load unique EIDs (inlined)
    logger.info("Loading unique session EIDs from bwm_df...")
    bwm_df = load_fixtures.load_bwm_df()
    all_eids = bwm_df.drop_duplicates("eid")["eid"].tolist()
    all_eids.sort()  # Deterministic ordering for reproducibility

    if args.stub_test:
        logger.info("STUB TEST MODE: Using first 10 sessions only")
        all_eids = all_eids[:10]

    logger.info(f"Total sessions: {len(all_eids)}")
    logger.info(f"Number of shards: {args.num_shards}")

    # Divide into chunks (inlined)
    logger.info("Dividing sessions into shards...")
    chunk_size = len(all_eids) // args.num_shards
    remainder = len(all_eids) % args.num_shards

    chunks = []
    start = 0
    for i in range(args.num_shards):
        end = start + chunk_size + (1 if i < remainder else 0)
        chunks.append(all_eids[start:end])
        start = end

    # Verify chunking
    sessions_per_shard = [len(chunk) for chunk in chunks]
    logger.info(f"Sessions per shard: min={min(sessions_per_shard)}, max={max(sessions_per_shard)}")

    # Write assignment files (inlined)
    logger.info(f"Writing assignment files to {OUTPUT_DIR}...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    written_paths = []
    for index, chunk in enumerate(chunks, start=1):
        filename = OUTPUT_DIR / f"chunk-{index:03d}.json"
        filename.write_text(json.dumps(chunk, indent=2))
        written_paths.append(filename)

    logger.info("=" * 80)
    logger.info("ASSIGNMENTS GENERATED")
    logger.info("=" * 80)
    logger.info(f"Total assignment files: {len(written_paths)}")
    logger.info(f"Output directory: {OUTPUT_DIR}")
    logger.info(f"First file: {written_paths[0]}")
    logger.info(f"Last file: {written_paths[-1]}")
    logger.info("\nDistribution:")
    for i, chunk in enumerate(chunks, start=1):
        logger.info(f"  Shard {i:03d}: {len(chunk)} sessions")
    logger.info("=" * 80)


if __name__ == "__main__":
    sys.exit(main())
