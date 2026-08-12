#!/bin/sh
# Smoke test a headlessvice image: tests/smoke.sh <image>
set -eu

image=${1:?usage: smoke.sh <image>}
here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)

fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "ok: $*"; }

ref=$(sed -n 's/^ARG ASID_VICE_REF=//p' "${here}/../Dockerfile")
ok "asid-vice $(echo "${ref}" | cut -c1-8)"

docker run --rm --entrypoint vsid "${image}" -help >/dev/null 2>&1 \
  || fail "vsid does not run"
ok "vsid runs"

# The bustrace sources are dropped silently if the automake regeneration in the
# Dockerfile stops taking effect: vsid then builds and runs, but rejects
# -bustrace at the command line. Assert the option is really there.
docker run --rm --entrypoint vsid "${image}" -help 2>&1 | grep -q bustrace \
  || fail "vsid was built without -bustrace"
ok "vsid offers -bustrace"

docker run --rm --entrypoint python3 "${image}" /usr/local/bin/vsiddump.py --help \
  >/dev/null 2>&1 || fail "vsiddump.py does not run"
ok "vsiddump.py runs"

echo "PASS ${image}"
