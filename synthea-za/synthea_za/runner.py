"""Build (if needed) and run Synthea once per province."""
from __future__ import annotations

import fnmatch
import os
import platform
import shutil
import subprocess
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from synthea_za.config import DEFAULT_JAR, SYNTHEA_ROOT, GenerationConfig, Province, allocate_patients
from synthea_za.overlay import OverlayPaths

# Built in Synthea modules that only make sense for the United States.
EXCLUDED_MODULE_PATTERNS = [
    "veteran*",
]


class RunnerError(RuntimeError):
    pass


@dataclass
class RunResult:
    province: Province
    patients: int
    seed: int
    output_dir: Path
    command: List[str]
    return_code: int
    seconds: float
    log_file: Path
    summary_lines: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.return_code == 0


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def ensure_java(java: str) -> str:
    resolved = shutil.which(java)
    if resolved is None:
        raise RunnerError(
            f"Java executable '{java}' was not found. Synthea needs a Java 17 or newer JDK; "
            "set JAVA or pass --java to point at one.")
    return resolved


def jar_is_stale(jar: Path, sources: Path = SYNTHEA_ROOT / "src" / "main") -> bool:
    """True when any Synthea source or resource file is newer than the built jar."""
    if not jar.is_file() or not sources.is_dir():
        return False
    built = jar.stat().st_mtime
    for path in sources.rglob("*"):
        if path.is_file() and path.stat().st_mtime > built:
            return True
    return False


def ensure_jar(config: GenerationConfig, force: bool = False) -> Path:
    """Return the path to the Synthea fat jar, building it with Gradle when missing.

    The default jar (built from the fork in the parent directory) is rebuilt when it is
    older than the Synthea sources, so changes to the fork are never silently ignored.
    A jar passed explicitly with ``--jar`` is used as it is.
    """
    jar = Path(config.jar)
    is_default = jar.resolve() == DEFAULT_JAR.resolve()
    if jar.is_file() and not force:
        if not (is_default and config.build_if_missing and jar_is_stale(jar)):
            return jar
        _log(f"Synthea jar at {jar} is older than the Synthea sources; rebuilding it")
    elif not jar.is_file():
        if not config.build_if_missing:
            raise RunnerError(f"Synthea jar not found at {jar}. Run 'synthea-za build-jar' first.")
        if not is_default:
            raise RunnerError(f"Synthea jar not found at {jar}. Pass an existing jar, or omit "
                              f"--jar to build {DEFAULT_JAR} with Gradle.")
    elif not is_default:
        raise RunnerError(f"Only the default jar {DEFAULT_JAR} can be built; {jar} was given.")
    gradlew = SYNTHEA_ROOT / ("gradlew.bat" if platform.system() == "Windows" else "gradlew")
    if not gradlew.exists():
        raise RunnerError(
            f"Synthea jar not found at {jar} and no Gradle wrapper at {gradlew}. "
            "Pass --jar to an existing synthea-with-dependencies.jar.")
    if not jar.is_file():
        _log(f"Synthea jar not found at {jar}; building it with {gradlew.name} uberJar "
             "(first build downloads dependencies and can take several minutes)")
    command = [str(gradlew), "uberJar", "-x", "test", "-x", "checkstyleMain",
               "-x", "checkstyleTest", "--no-daemon"]
    env = dict(os.environ)
    java = Path(ensure_java(config.java)).resolve()
    if java.parent.name == "bin":
        # let the Gradle wrapper find the same JDK that will run Synthea
        env.setdefault("JAVA_HOME", str(java.parent.parent))
    completed = subprocess.run(command, cwd=str(SYNTHEA_ROOT), env=env)
    if completed.returncode != 0 or not jar.is_file():
        raise RunnerError("Gradle build failed; see the output above.")
    return jar


def list_top_level_modules(jar: Path, local_modules: Optional[Path]) -> List[str]:
    """Names of the top level generic modules available to a run."""
    names = set()
    with zipfile.ZipFile(jar) as archive:
        for entry in archive.namelist():
            if entry.startswith("modules/") and entry.endswith(".json") and entry.count("/") == 1:
                names.add(entry[len("modules/"):-len(".json")])
    if local_modules and local_modules.is_dir():
        for path in local_modules.glob("*.json"):
            names.add(path.stem)
    return sorted(names)


def enabled_modules(jar: Path, local_modules: Optional[Path],
                    excluded_patterns: Iterable[str] = EXCLUDED_MODULE_PATTERNS) -> List[str]:
    patterns = list(excluded_patterns)
    return [name for name in list_top_level_modules(jar, local_modules)
            if not any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)]


def build_command(config: GenerationConfig, overlay: OverlayPaths, jar: Path,
                  province: Province, patients: int, seed: int, clinician_seed: int,
                  output_dir: Path, modules: Optional[List[str]] = None) -> List[str]:
    classpath = os.pathsep.join([str(overlay.overlay_dir.resolve()), str(jar.resolve())])
    command = [ensure_java(config.java), *config.java_opts, "-cp", classpath, "App",
               "-p", str(patients), "-s", str(seed), "-cs", str(clinician_seed),
               "-c", str(overlay.properties_file.resolve())]
    if overlay.local_modules_dir is not None:
        command += ["-d", str(overlay.local_modules_dir.resolve())]
    if modules:
        command += ["-m", os.pathsep.join(modules)]
    if config.reference_date:
        # -r only moves the age reference; -e ends the simulation and the export window
        command += ["-r", config.reference_date, "-e", config.end_date or config.reference_date]
    elif config.end_date:
        command += ["-e", config.end_date]
    if config.age_range:
        command += ["-a", config.age_range]
    if config.gender:
        command += ["-g", config.gender]
    command.append(f"--exporter.baseDirectory={output_dir.resolve().as_posix()}/")
    if overlay.module_overrides_file is not None:
        command.append(f"--module_override={overlay.module_overrides_file.resolve().as_posix()}")
    command += list(config.synthea_args)
    command.append(province.name)
    if config.city:
        command.append(config.city)
    return command


def run_province(config: GenerationConfig, overlay: OverlayPaths, jar: Path,
                 province: Province, patients: int, seed: int,
                 modules: Optional[List[str]]) -> RunResult:
    output_dir = config.raw_dir / province.code
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    clinician_seed = (config.clinician_seed if config.clinician_seed is not None else seed) + 1000
    command = build_command(config, overlay, jar, province, patients, seed, clinician_seed,
                            output_dir, modules)
    log_file = output_dir / "synthea.log"
    _log(f"[{province.name}] generating {patients} patient(s) with seed {seed}")
    started = time.time()
    summary: List[str] = []
    with log_file.open("w", encoding="utf-8") as log:
        log.write(" ".join(command) + "\n\n")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace",
                                   cwd=str(overlay.overlay_dir.parent))
        assert process.stdout is not None
        for line in process.stdout:
            log.write(line)
            text = line.rstrip()
            if text.startswith("Records:") or text.startswith("ERROR") \
                    or "Exception" in text or text.startswith("Scanned"):
                summary.append(text)
                _log(f"[{province.name}] {text}")
        return_code = process.wait()
    seconds = time.time() - started
    if return_code == 0 and not any(line.startswith("Records:") for line in summary):
        # Synthea exits 0 after an argument or configuration error without generating anything
        return_code = 1
        summary.append("Synthea produced no records (argument or configuration error)")
    if return_code != 0:
        _log(f"[{province.name}] Synthea exited with code {return_code}; see {log_file}")
    else:
        _log(f"[{province.name}] done in {seconds:.0f}s")
    return RunResult(province, patients, seed, output_dir, command, return_code, seconds,
                     log_file, summary)


def run_all(config: GenerationConfig, overlay: OverlayPaths, jar: Path) -> List[RunResult]:
    allocation: Dict[str, int] = allocate_patients(config.patients, config.provinces)
    if not allocation:
        raise RunnerError("No patients to generate (allocation is empty).")
    modules = enabled_modules(jar, overlay.local_modules_dir)
    plan = []
    for index, province in enumerate(config.provinces):
        count = allocation.get(province.name, 0)
        if count > 0:
            plan.append((province, count, config.seed + index))
    _log("Allocation: " + ", ".join(f"{p.name}={n}" for p, n, _ in plan))
    results: List[RunResult] = []
    if config.jobs > 1 and len(plan) > 1:
        with ThreadPoolExecutor(max_workers=config.jobs) as pool:
            futures = [pool.submit(run_province, config, overlay, jar, p, n, s, modules)
                       for p, n, s in plan]
            results = [f.result() for f in futures]
    else:
        for province, count, seed in plan:
            results.append(run_province(config, overlay, jar, province, count, seed, modules))
    return results
