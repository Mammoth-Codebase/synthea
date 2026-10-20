"""Command line interface for synthea-za."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import date
from pathlib import Path
from typing import List, Optional

from synthea_za import __version__
from synthea_za.config import (DATA_DIR, DEFAULT_JAR, PROVINCES, GenerationConfig,
                               PostProcessOptions, allocate_patients, find_province)
from synthea_za.loader import LoadOptions, load_directory
from synthea_za.overlay import build_overlay
from synthea_za.postprocess import PostProcessOptions as _PPO  # noqa: F401  (re-export for tests)
from synthea_za.postprocess import copy_other_outputs, process_directory
from synthea_za.report import render_markdown, summarise
from synthea_za.runner import RunnerError, ensure_jar, ensure_java, run_all
from synthea_za.validate import PART_KINDS, validate_data_dir, validate_part


def _add_postprocess_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("post-processing")
    group.add_argument("--no-national-id", action="store_true",
                       help="keep Synthea's US social security identifier instead of adding a South African ID number")
    group.add_argument("--national-id-system", default=PostProcessOptions.national_id_system,
                       help="identifier.system for the South African ID number")
    group.add_argument("--passport-system", default=PostProcessOptions.passport_system)
    group.add_argument("--practitioner-system", default=PostProcessOptions.practitioner_system,
                       help="identifier.system for practitioner registration numbers")
    group.add_argument("--mrn-system", default=None,
                       help="replace the medical record number system (default keeps Synthea's)")
    group.add_argument("--keep-drivers-licence", action="store_true",
                       help="keep the US driver's licence identifier")
    group.add_argument("--no-phones", action="store_true", help="keep US style telephone numbers")
    group.add_argument("--currency", default="ZAR",
                       help="currency code for money values; use USD to leave amounts unchanged")
    group.add_argument("--zar-per-usd", type=float, default=PostProcessOptions.zar_per_usd,
                       help="exchange rate applied to Synthea's USD cost model")
    group.add_argument("--no-si-units", action="store_true",
                       help="leave chemistry results in mg/dL instead of converting to mmol/L")
    group.add_argument("--meta-tag", default=None,
                       help="add a meta.tag with this code to every resource")


def _postprocess_options(args: argparse.Namespace) -> PostProcessOptions:
    currency = None if args.currency.upper() == "USD" else args.currency.upper()
    return PostProcessOptions(
        national_id=not args.no_national_id,
        national_id_system=args.national_id_system,
        passport_system=args.passport_system,
        practitioner_system=args.practitioner_system,
        mrn_system=args.mrn_system,
        phones=not args.no_phones,
        currency=currency,
        zar_per_usd=args.zar_per_usd,
        si_units=not args.no_si_units,
        drop_drivers_licence=not args.keep_drivers_licence,
        meta_tag=args.meta_tag,
    )


def _key_value(item: str) -> str:
    """argparse type for KEY=VALUE arguments."""
    if "=" not in item or not item.split("=", 1)[0].strip():
        raise argparse.ArgumentTypeError(f"expected KEY=VALUE, got '{item}'")
    return item


def _parse_properties(values: Optional[List[str]]) -> dict:
    properties = {}
    for item in values or []:
        key, value = item.split("=", 1)
        properties[key.strip()] = value.strip()
    return properties


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="synthea-za",
        description="Generate a South African synthetic patient population with Synthea and "
                    "export FHIR R4 bundles for InterSystems HealthShare.")
    parser.add_argument("--version", action="version", version=f"synthea-za {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="generate patients and FHIR bundles")
    gen.add_argument("-p", "--patients", type=int, required=True, help="number of patients to generate")
    gen.add_argument("-o", "--output", type=Path, default=Path("output"), help="output directory (default ./output)")
    gen.add_argument("-s", "--seed", type=int, default=1, help="random seed (default 1)")
    gen.add_argument("--clinician-seed", type=int, default=None)
    gen.add_argument("--province", action="append", default=None,
                     help="restrict generation to a province (name or code); may be repeated")
    gen.add_argument("--city", default=None, help="restrict generation to one town (requires a single --province)")
    gen.add_argument("--years-of-history", type=int, default=10,
                     help="years of history to keep in the exported records (default 10)")
    gen.add_argument("--reference-date", default=None, help="end of the simulation as YYYYMMDD (default today)")
    gen.add_argument("--age-range", default=None, help="limit patient ages, e.g. 18-65")
    gen.add_argument("--gender", choices=["M", "F"], default=None)
    gen.add_argument("--only-alive", action="store_true", help="only export patients alive at the reference date")
    gen.add_argument("--keep-old-deaths", action="store_true",
                     help="also export patients who died before the history window (they have almost no records)")
    gen.add_argument("--jar", type=Path, default=DEFAULT_JAR, help="path to synthea-with-dependencies.jar")
    gen.add_argument("--java", default=os.environ.get("JAVA", "java"),
                     help="java executable (default: $JAVA or java on PATH)")
    gen.add_argument("--java-opt", action="append", default=[], help="extra JVM option, written as --java-opt=-Xmx8g (repeatable)")
    gen.add_argument("--no-build", action="store_true", help="fail instead of building the jar when it is missing")
    gen.add_argument("--jobs", type=int, default=1, help="number of provinces to simulate concurrently")
    gen.add_argument("--keep-raw", action="store_true", help="keep Synthea's unprocessed output under <output>/.work")
    gen.add_argument("--clinical-notes", action="store_true", help="also export clinical notes (DocumentReference)")
    gen.add_argument("--csv", action="store_true", help="also export Synthea CSV tables")
    gen.add_argument("--property", action="append", default=[], metavar="KEY=VALUE", type=_key_value,
                     help="override any synthea.properties setting (repeatable)")
    gen.add_argument("--synthea-arg", action="append", default=[], help="extra argument passed to Synthea verbatim")
    gen.add_argument("--no-report", action="store_true", help="skip the corpus summary report")
    _add_postprocess_arguments(gen)

    build = sub.add_parser("build-jar", help="build the Synthea jar with Gradle")
    build.add_argument("--jar", type=Path, default=DEFAULT_JAR)
    build.add_argument("--java", default=os.environ.get("JAVA", "java"),
                       help="java executable used for the build (default: $JAVA or java on PATH)")

    val = sub.add_parser("validate-data", help="validate the South African reference data")
    val.add_argument("--data-dir", type=Path, default=DATA_DIR)
    val.add_argument("--strict", action="store_true", help="treat warnings as errors")

    part = sub.add_parser("validate-part", help="validate a single source file from data_src")
    part.add_argument("kind", choices=list(PART_KINDS))
    part.add_argument("file", type=Path)
    part.add_argument("--province", default=None, help="province name the file must belong to")

    post = sub.add_parser("postprocess", help="apply South African post-processing to existing Synthea FHIR output")
    post.add_argument("input", type=Path, help="directory containing Synthea FHIR bundles")
    post.add_argument("output", type=Path, help="directory to write processed bundles to")
    post.add_argument("--label", default=None, help="label used to rename organisation and practitioner bundles")
    _add_postprocess_arguments(post)

    rep = sub.add_parser("report", help="summarise a directory of generated bundles")
    rep.add_argument("fhir_dir", type=Path)
    rep.add_argument("--json", action="store_true", help="print JSON instead of markdown")

    load = sub.add_parser("load", help="POST the bundles to a FHIR R4 server (e.g. HealthShare)")
    load.add_argument("fhir_dir", type=Path)
    load.add_argument("--url", required=True, help="FHIR base URL, e.g. https://host/csp/healthshare/hsfhir/fhir/r4")
    load.add_argument("--username", default=None)
    load.add_argument("--password", default=None)
    load.add_argument("--token", default=None, help="bearer token")
    load.add_argument("--header", action="append", default=[], metavar="NAME=VALUE", type=_key_value)
    load.add_argument("--timeout", type=int, default=300)
    load.add_argument("--retries", type=int, default=2)
    load.add_argument("--dry-run", action="store_true")
    load.add_argument("--stop-on-error", action="store_true")

    sub.add_parser("provinces", help="list provinces and the patient allocation weights")
    return parser


def command_generate(args: argparse.Namespace) -> int:
    provinces = list(PROVINCES)
    if args.province:
        provinces = list(dict.fromkeys(find_province(p) for p in args.province))
    if args.city and len(provinces) != 1:
        print("--city requires exactly one --province", file=sys.stderr)
        return 2
    if args.patients < 1:
        print("--patients must be at least 1", file=sys.stderr)
        return 2
    output = Path(args.output).resolve()
    config = GenerationConfig(
        patients=args.patients,
        output_dir=output,
        seed=args.seed,
        clinician_seed=args.clinician_seed,
        provinces=provinces,
        city=args.city,
        years_of_history=args.years_of_history,
        reference_date=args.reference_date,
        age_range=args.age_range,
        gender=args.gender,
        only_alive=args.only_alive,
        jar=Path(args.jar),
        java=args.java,
        java_opts=list(args.java_opt),
        build_if_missing=not args.no_build,
        keep_raw=args.keep_raw,
        jobs=max(1, args.jobs),
        clinical_notes=args.clinical_notes,
        csv_export=args.csv,
        extra_properties=_parse_properties(args.property),
        synthea_args=list(args.synthea_arg),
        postprocess=_postprocess_options(args),
    )
    started = time.time()
    try:
        ensure_java(config.java)
        jar = ensure_jar(config)
    except RunnerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    validation = validate_data_dir(DATA_DIR)
    for issue in validation.errors:
        print(str(issue), file=sys.stderr)
    if not validation.ok:
        print("error: reference data failed validation; aborting", file=sys.stderr)
        return 1

    output.mkdir(parents=True, exist_ok=True)
    fhir_out = output / "fhir"
    if fhir_out.exists():
        shutil.rmtree(fhir_out)
    fhir_out.mkdir()
    for stale in ("csv", "metadata", "notes"):
        shutil.rmtree(output / stale, ignore_errors=True)
    for stale_file in ("summary.json", "summary.md", "manifest.json"):
        (output / stale_file).unlink(missing_ok=True)
    overlay = build_overlay(config)
    try:
        results = run_all(config, overlay, jar)
    except RunnerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    used_ids = set()
    stats = None
    deceased_cutoff = None
    reference = (date(int(args.reference_date[:4]), int(args.reference_date[4:6]), int(args.reference_date[6:8]))
                 if args.reference_date else date.today())
    if not args.keep_old_deaths:
        try:
            deceased_cutoff = reference.replace(year=reference.year - config.years_of_history)
        except ValueError:  # 29 February
            deceased_cutoff = reference.replace(year=reference.year - config.years_of_history, day=28)
    manifest = {"version": __version__, "generated_at": date.today().isoformat(),
                "patients_requested": config.patients, "seed": config.seed,
                "years_of_history": config.years_of_history, "runs": [], "postprocess": None}
    failures = 0
    for result in results:
        run_entry = {"province": result.province.name, "code": result.province.code,
                     "patients": result.patients, "seed": result.seed,
                     "return_code": result.return_code, "seconds": round(result.seconds, 1),
                     "summary": result.summary_lines, "command": result.command}
        manifest["runs"].append(run_entry)
        if not result.ok:
            failures += 1
            continue
        raw_fhir = result.output_dir / "fhir"
        if raw_fhir.is_dir():
            stats = process_directory(raw_fhir, fhir_out, config.postprocess,
                                      label=result.province.code, used_ids=used_ids, stats=stats,
                                      deceased_cutoff=deceased_cutoff)
        copy_other_outputs(result.output_dir, output, result.province.code)
    if stats is not None:
        manifest["postprocess"] = stats.as_dict()
    manifest["seconds"] = round(time.time() - started, 1)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if not args.no_report and stats is not None and stats.patients:
        summary = summarise(fhir_out, reference=reference)
        (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        (output / "summary.md").write_text(render_markdown(summary), encoding="utf-8")

    if not config.keep_raw:
        shutil.rmtree(config.raw_dir, ignore_errors=True)
        shutil.rmtree(config.overlay_dir.parent, ignore_errors=True)

    produced = stats.patients if stats else 0
    skipped = stats.skipped_deceased if stats else 0
    print(f"Generated {produced} patient bundle(s) in {fhir_out} "
          f"({manifest['seconds']}s, {failures} failed province run(s), "
          f"{skipped} patient(s) who died before the history window left out)")
    if failures:
        print("Some provinces failed; see manifest.json and the synthea.log files "
              "(re-run with --keep-raw to retain them)", file=sys.stderr)
        return 1
    return 0


def command_build(args: argparse.Namespace) -> int:
    config = GenerationConfig(patients=0, output_dir=Path("."), jar=Path(args.jar), java=args.java,
                              build_if_missing=True)
    try:
        jar = ensure_jar(config, force=True)
    except RunnerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Synthea jar ready at {jar}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    result = validate_data_dir(Path(args.data_dir))
    for issue in result.issues:
        print(str(issue))
    for key, value in result.counts.items():
        print(f"{key}: {value}")
    failed = not result.ok or (args.strict and result.issues)
    print("FAILED" if failed else "OK")
    return 1 if failed else 0


def command_validate_part(args: argparse.Namespace) -> int:
    province = find_province(args.province).name if args.province else None
    result = validate_part(args.kind, Path(args.file), province)
    for issue in result.issues:
        print(str(issue))
    for key, value in result.counts.items():
        print(f"{key}: {value}")
    print("OK" if result.ok else "FAILED")
    return 0 if result.ok else 1


def command_postprocess(args: argparse.Namespace) -> int:
    stats = process_directory(Path(args.input), Path(args.output), _postprocess_options(args),
                              label=args.label)
    print(json.dumps(stats.as_dict(), indent=2))
    return 0


def command_report(args: argparse.Namespace) -> int:
    summary = summarise(Path(args.fhir_dir))
    print(json.dumps(summary, indent=2) if args.json else render_markdown(summary))
    return 0


def command_load(args: argparse.Namespace) -> int:
    headers = dict(h.split("=", 1) for h in args.header)
    options = LoadOptions(base_url=args.url, username=args.username, password=args.password,
                          token=args.token, headers=headers, timeout=args.timeout,
                          retries=args.retries, dry_run=args.dry_run, stop_on_error=args.stop_on_error)
    results = load_directory(Path(args.fhir_dir), options)
    print(json.dumps(results))
    return 1 if results["failed"] else 0


def command_provinces(_: argparse.Namespace) -> int:
    allocation = allocate_patients(1000)
    print(f"{'Province':<16}{'Code':<6}{'Population':>12}{'Per 1000 patients':>20}")
    for province in PROVINCES:
        print(f"{province.name:<16}{province.code:<6}{province.population:>12,}{allocation.get(province.name, 0):>20}")
    return 0


COMMANDS = {
    "generate": command_generate,
    "build-jar": command_build,
    "validate-data": command_validate,
    "validate-part": command_validate_part,
    "postprocess": command_postprocess,
    "report": command_report,
    "load": command_load,
    "provinces": command_provinces,
}


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
