#!/usr/bin/env bash
# run_local.sh : set up and run the South African Synthea generator on a Mac (or Linux).
#
#   ./run_local.sh [PATIENTS] [OUTPUT_DIR]
#
# Examples
#   ./run_local.sh                      # 200 patients into ./output
#   ./run_local.sh 1000 ~/sa-corpus     # 1000 patients into ~/sa-corpus
#   EXTRA_ARGS="--province GP --csv" ./run_local.sh 50
#
# Optional environment variables
#   REPO_DIR        where to clone or find the Synthea fork (default: the checkout this
#                   script lives in, otherwise ~/synthea)
#   REPO_URL        clone URL (default: https://github.com/Mammoth-Codebase/synthea.git)
#   BRANCH          git branch to use (default: claude/sa-synthea-population-generator-gu33o7)
#   JOBS            provinces simulated at the same time (default: cores - 1, at most 4)
#   JAVA_HEAP       JVM heap per province run (default: 3g)
#   SEED            random seed (default: 1)
#   EXTRA_ARGS      extra arguments for "synthea-za generate", e.g. "--province WC --csv"
#   JAVA_HOME       JDK 17 or newer to use (auto-detected when unset)
#   INSTALL_DEPS=1  install a missing JDK or Python with Homebrew instead of stopping
#   HEALTHSHARE_URL plus HEALTHSHARE_USER/HEALTHSHARE_PASSWORD or HEALTHSHARE_TOKEN
#                   load the bundles into HealthShare after generating them
set -euo pipefail

PATIENTS="${1:-200}"
OUTPUT_DIR="${2:-$PWD/output}"
BRANCH="${BRANCH:-claude/sa-synthea-population-generator-gu33o7}"
REPO_URL="${REPO_URL:-https://github.com/Mammoth-Codebase/synthea.git}"
SEED="${SEED:-1}"
JAVA_HEAP="${JAVA_HEAP:-3g}"
EXTRA_ARGS="${EXTRA_ARGS:-}"

say() { printf '\n==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

case "$PATIENTS" in
  ''|*[!0-9]*) die "PATIENTS must be a whole number, got '$PATIENTS'" ;;
esac

# ---------------------------------------------------------------- 1. the repository
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/pyproject.toml" ] && [ -f "$SCRIPT_DIR/../gradlew" ]; then
  REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
else
  REPO_DIR="${REPO_DIR:-$HOME/synthea}"
fi

command -v git >/dev/null 2>&1 || die "git is not installed (on a Mac run: xcode-select --install)"

if [ ! -d "$REPO_DIR/.git" ]; then
  say "Cloning $REPO_URL into $REPO_DIR"
  git clone --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
else
  say "Using the checkout in $REPO_DIR"
  current="$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"
  if [ "$current" != "$BRANCH" ]; then
    git -C "$REPO_DIR" fetch origin "$BRANCH"
    git -C "$REPO_DIR" checkout "$BRANCH"
  fi
  git -C "$REPO_DIR" pull --ff-only origin "$BRANCH" \
    || echo "warning: could not fast-forward $BRANCH; continuing with the local copy"
fi
PROJECT_DIR="$REPO_DIR/synthea-za"
[ -f "$PROJECT_DIR/pyproject.toml" ] || die "$PROJECT_DIR does not contain the generator; is BRANCH right?"

# ---------------------------------------------------------------- 2. Java 17 or newer
java_major() {
  local v
  v="$("$1" -version 2>&1 | awk -F'"' '/version/ {print $2; exit}')" || true
  v="${v#1.}"
  v="${v%%.*}"
  v="$(printf '%s' "$v" | tr -dc '0-9')"
  echo "${v:-0}"
}

find_java() {
  local candidates=() jh j
  [ -n "${JAVA_HOME:-}" ] && candidates+=("$JAVA_HOME/bin/java")
  if [ -x /usr/libexec/java_home ]; then
    jh="$(/usr/libexec/java_home -v 17+ 2>/dev/null || true)"
    [ -n "$jh" ] && candidates+=("$jh/bin/java")
  fi
  for prefix in /opt/homebrew /usr/local; do
    for keg in openjdk openjdk@25 openjdk@21 openjdk@17; do
      candidates+=("$prefix/opt/$keg/bin/java")
    done
  done
  command -v java >/dev/null 2>&1 && candidates+=("$(command -v java)")
  for j in "${candidates[@]}"; do
    [ -x "$j" ] || continue
    if [ "$(java_major "$j")" -ge 17 ]; then
      echo "$j"
      return 0
    fi
  done
  return 1
}

JAVA_BIN="$(find_java || true)"
if [ -z "$JAVA_BIN" ]; then
  if [ "${INSTALL_DEPS:-0}" = "1" ] && command -v brew >/dev/null 2>&1; then
    say "Installing OpenJDK 21 with Homebrew"
    brew install openjdk@21
    JAVA_BIN="$(find_java || true)"
  fi
  [ -n "$JAVA_BIN" ] || die "no Java 17+ JDK found. Install one with 'brew install openjdk@21' \
(or download from https://adoptium.net) and rerun, or rerun with INSTALL_DEPS=1."
fi
JAVA_HOME="$("$JAVA_BIN" -XshowSettings:properties -version 2>&1 | awk '/java.home/ {print $3; exit}')"
export JAVA_HOME
export PATH="$JAVA_HOME/bin:$PATH"
say "Using Java $(java_major "$JAVA_BIN") at $JAVA_HOME"

# ---------------------------------------------------------------- 3. Python 3.9 or newer
find_python() {
  local p
  for p in python3 python3.13 python3.12 python3.11 python3.10 python3.9 python; do
    if command -v "$p" >/dev/null 2>&1 \
       && "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
      command -v "$p"
      return 0
    fi
  done
  return 1
}
PYTHON="$(find_python || true)"
if [ -z "$PYTHON" ]; then
  if [ "${INSTALL_DEPS:-0}" = "1" ] && command -v brew >/dev/null 2>&1; then
    say "Installing Python with Homebrew"
    brew install python
    PYTHON="$(find_python || true)"
  fi
  [ -n "$PYTHON" ] || die "no Python 3.9+ found. Install it with 'brew install python' and rerun."
fi
say "Using $("$PYTHON" --version) at $PYTHON"
# the generator has no third party dependencies, so it runs straight from the checkout
export PYTHONPATH="$PROJECT_DIR${PYTHONPATH:+:$PYTHONPATH}"
synthea_za() { "$PYTHON" -m synthea_za "$@"; }

# ---------------------------------------------------------------- 4. concurrency
if [ -z "${JOBS:-}" ]; then
  cores="$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 2)"
  JOBS=$(( cores - 1 ))
  [ "$JOBS" -lt 1 ] && JOBS=1
  [ "$JOBS" -gt 4 ] && JOBS=4
fi

# ---------------------------------------------------------------- 5. generate
if [ ! -f "$REPO_DIR/build/libs/synthea-with-dependencies.jar" ]; then
  say "First run: the Synthea jar will be built with Gradle (several minutes, needs internet)"
fi
mkdir -p "$OUTPUT_DIR"
say "Generating $PATIENTS patients into $OUTPUT_DIR ($JOBS province run(s) at a time, seed $SEED)"
# shellcheck disable=SC2086
synthea_za generate --patients "$PATIENTS" --output "$OUTPUT_DIR" --seed "$SEED" \
  --jobs "$JOBS" --java "$JAVA_BIN" "--java-opt=-Xmx$JAVA_HEAP" $EXTRA_ARGS

say "Done. Bundles are in $OUTPUT_DIR/fhir, summary in $OUTPUT_DIR/summary.md"
if [ -f "$OUTPUT_DIR/summary.md" ]; then
  head -n 12 "$OUTPUT_DIR/summary.md"
fi

# ---------------------------------------------------------------- 6. optional HealthShare load
if [ -n "${HEALTHSHARE_URL:-}" ]; then
  say "Loading the bundles into $HEALTHSHARE_URL"
  load_args=(load "$OUTPUT_DIR/fhir" --url "$HEALTHSHARE_URL")
  if [ -n "${HEALTHSHARE_TOKEN:-}" ]; then
    load_args+=(--token "$HEALTHSHARE_TOKEN")
  elif [ -n "${HEALTHSHARE_USER:-}" ]; then
    load_args+=(--username "$HEALTHSHARE_USER" --password "${HEALTHSHARE_PASSWORD:-}")
  fi
  synthea_za "${load_args[@]}"
fi
