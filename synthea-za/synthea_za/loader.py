"""Load generated bundles into a FHIR R4 server such as InterSystems HealthShare.

Bundles are transaction bundles, so each file is POSTed to the server base URL.
Organisation and practitioner bundles are sent first because patient bundles reference
them.
"""
from __future__ import annotations

import base64
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from synthea_za.postprocess import is_patient_bundle


@dataclass
class LoadOptions:
    base_url: str
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    timeout: int = 300
    retries: int = 2
    dry_run: bool = False
    stop_on_error: bool = False


def ordered_bundle_files(fhir_dir: Path) -> List[Path]:
    files = sorted(fhir_dir.glob("*.json"))
    hospitals = [f for f in files if f.name.startswith("hospitalInformation")]
    practitioners = [f for f in files if f.name.startswith("practitionerInformation")]
    patients = [f for f in files if is_patient_bundle(f)]
    return hospitals + practitioners + patients


def _request(options: LoadOptions, body: bytes) -> urllib.request.Request:
    url = options.base_url.rstrip("/") + "/"
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/fhir+json")
    request.add_header("Accept", "application/fhir+json")
    if options.token:
        request.add_header("Authorization", f"Bearer {options.token}")
    elif options.username is not None:
        credentials = base64.b64encode(f"{options.username}:{options.password or ''}".encode()).decode()
        request.add_header("Authorization", f"Basic {credentials}")
    for key, value in (options.headers or {}).items():
        request.add_header(key, value)
    return request


def load_directory(fhir_dir: Path, options: LoadOptions) -> Dict[str, int]:
    files = ordered_bundle_files(fhir_dir)
    results = {"sent": 0, "failed": 0, "skipped": 0}
    for path in files:
        body = path.read_bytes()
        if options.dry_run:
            print(f"[dry-run] would POST {path.name} ({len(body)} bytes)")
            results["skipped"] += 1
            continue
        attempt = 0
        while True:
            attempt += 1
            try:
                with urllib.request.urlopen(_request(options, body), timeout=options.timeout) as response:
                    status = response.status
                    payload = response.read()
                outcome = ""
                try:
                    parsed = json.loads(payload)
                    if parsed.get("resourceType") == "OperationOutcome":
                        outcome = " " + json.dumps(parsed)[:300]
                except ValueError:
                    pass
                print(f"{path.name}: HTTP {status}{outcome}")
                results["sent"] += 1
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                print(f"{path.name}: HTTP {exc.code} {detail}", file=sys.stderr)
                if attempt > options.retries:
                    results["failed"] += 1
                    if options.stop_on_error:
                        return results
                    break
                time.sleep(2 * attempt)
            except (urllib.error.URLError, TimeoutError) as exc:
                print(f"{path.name}: {exc}", file=sys.stderr)
                if attempt > options.retries:
                    results["failed"] += 1
                    if options.stop_on_error:
                        return results
                    break
                time.sleep(2 * attempt)
    return results
