"""Send a log file or JSON events to a running AEIP intelligence service.

Examples:
    python scripts/send_events.py --repository acme/shop --logs app.log --source app --service api
    python scripts/send_events.py --repository acme/shop --logs postgres.log --source database
    python scripts/send_events.py --repository acme/shop --events deploys.json
    python scripts/send_events.py --repository acme/shop --events alert.json --format alertmanager

Set AEIP_INGEST_KEY if the service requires it, and AEIP_API_URL if it is not on localhost:8001.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repository", required=True, help="owner/name the events belong to")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--logs", type=Path, help="plain-text or JSON-lines log file")
    group.add_argument("--events", type=Path, help="JSON file: an event, a list, or a webhook payload")
    parser.add_argument("--format", default="generic",
                        help="for --events: generic, vercel, render, sentry, github or alertmanager")
    parser.add_argument("--source", default="app", help="for --logs: app, database, deploy, infra ...")
    parser.add_argument("--service", default="", help="service name shown on the timeline")
    parser.add_argument("--environment", default="production")
    parser.add_argument("--min-severity", default="warning", help="for --logs: lowest level to keep")
    args = parser.parse_args()

    base = os.environ.get("AEIP_API_URL", "http://localhost:8001").rstrip("/")
    headers = {"X-AEIP-Key": os.environ["AEIP_INGEST_KEY"]} if os.environ.get("AEIP_INGEST_KEY") else {}
    if args.logs:
        query = urllib.parse.urlencode({"repository": args.repository, "source": args.source, "service": args.service,
                                        "environment": args.environment, "minSeverity": args.min_severity})
        url, data, headers["Content-Type"] = f"{base}/api/events/logs?{query}", args.logs.read_bytes(), "text/plain"
    else:
        suffix = "" if args.format == "generic" else f"/{args.format}"
        url = f"{base}/api/events{suffix}?{urllib.parse.urlencode({'repository': args.repository})}"
        data, headers["Content-Type"] = json.dumps(json.loads(args.events.read_text(encoding="utf-8"))).encode(), "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request) as response:
            print(json.loads(response.read()))
            return 0
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode(errors='replace')}", file=sys.stderr)
    except urllib.error.URLError as exc:
        print(f"Could not reach {base}: {exc.reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
