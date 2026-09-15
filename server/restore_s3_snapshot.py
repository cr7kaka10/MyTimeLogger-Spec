"""Verify and extract an S3 SQLite snapshot without replacing production DB."""
import argparse
import sys

try:
    from .webdav_backup import restore_snapshot
except ImportError:
    from webdav_backup import restore_snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True, help="Downloaded .db.gz snapshot")
    parser.add_argument("--manifest", required=True, help="Downloaded manifest JSON")
    parser.add_argument("--output", required=True, help="New SQLite output path")
    args = parser.parse_args()
    result = restore_snapshot(args.snapshot, args.manifest, args.output)
    print(f"Verified restore complete: {result['count']} tables -> {result['output']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Restore failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
