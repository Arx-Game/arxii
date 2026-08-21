#!/usr/bin/env bash
# arx1-freeze.sh — one-time freeze of the Arx I game data into durable,
# checksummed archive artifacts. Runs ON the Arx I host (copy this file
# there), NOT on the Arx II box and not in a devcontainer. Produces, under
# $ARX1_OUT:
#
#   arx1-final-<date>.sqlite3.zst          consistent, vacuumed sqlite snapshot
#   arx1-rpevents-public-<date>.tar.zst    public rpevent logs
#   arx1-rpevents-gm-<date>.tar.zst        GM/OOC rpevent logs — PRIVATE:
#                                          backup-only, never served from the
#                                          archive site
#   arx1-resurrection-kit-<date>.tar.zst   game dir (venv included) + configs +
#                                          pip freeze + service/cron state:
#                                          everything needed to ever run the
#                                          game again
#   SHA256SUMS, README.txt
#
# Compression is LOSSLESS at every level — max settings cost CPU once, never
# fidelity. Separate tarballs on purpose: corruption in one compressed
# stream cannot take the others with it, and the GM set can never ship
# accidentally with anything public-facing.
#
# Companion: arx1-upload.sh pushes the lot to both buckets and verifies.
# Full runbook: docs/operations/arx1-archival.md.
set -euo pipefail

: "${ARX1_GAME_DIR:?set ARX1_GAME_DIR to the Arx I game directory (the evennia game dir)}"
: "${ARX1_LOG_DIR:?set ARX1_LOG_DIR to the directory holding the rpevent logs}"
ARX1_DB="${ARX1_DB:-${ARX1_GAME_DIR}/server/evennia.db3}"
# Filename pattern (a `find -name` glob, matched within ARX1_LOG_DIR) that
# identifies the GM/OOC variant of each event log. Everything else in the
# log dir counts as public. CHECK THIS against the real filenames before
# running — a wrong glob silently misfiles GM logs as public.
ARX1_GM_LOG_GLOB="${ARX1_GM_LOG_GLOB:-*_gm*}"
ARX1_VENV="${ARX1_VENV:-}" # optional: the game's virtualenv, for pip freeze
ARX1_OUT="${ARX1_OUT:-${HOME}/arx1-freeze}"

# -19: max practical level. --long=27: 128MB match window — event logs
# repeat heavily across files, and a long window lets zstd deduplicate
# across the whole tar stream. NOTE: decompression needs the same flag
# (`zstd -d --long=27`), recorded in README.txt below.
ZSTD_ARGS=(-19 --long=27 -T0)

for tool in sqlite3 zstd tar sha256sum; do
  command -v "${tool}" >/dev/null 2>&1 || {
    echo "required tool '${tool}' not found — install it first (apt install ${tool})" >&2
    exit 1
  }
done
[ -f "${ARX1_DB}" ] || { echo "ARX1_DB not found: ${ARX1_DB}" >&2; exit 1; }
[ -d "${ARX1_LOG_DIR}" ] || { echo "ARX1_LOG_DIR not found: ${ARX1_LOG_DIR}" >&2; exit 1; }

date_tag="$(date +%Y%m%d)"
mkdir -p "${ARX1_OUT}"
cd "${ARX1_OUT}"

echo "== 1/4 sqlite snapshot =="
# .backup uses sqlite's online-backup API: a CONSISTENT copy even if the
# game is still running (a raw `cp` of a live db is not). VACUUM then drops
# years of free pages from the copy before compression even starts.
db_snap="arx1-final-${date_tag}.sqlite3"
rm -f "${db_snap}"
sqlite3 "${ARX1_DB}" ".backup '${ARX1_OUT}/${db_snap}'"
sqlite3 "${ARX1_OUT}/${db_snap}" "VACUUM;"
integrity="$(sqlite3 "${ARX1_OUT}/${db_snap}" "PRAGMA integrity_check;")"
[ "${integrity}" = "ok" ] || { echo "sqlite integrity_check failed: ${integrity}" >&2; exit 1; }
zstd "${ZSTD_ARGS[@]}" --rm -f "${db_snap}" -o "${db_snap}.zst"
echo "   ${db_snap}.zst ($(du -h "${db_snap}.zst" | cut -f1))"

echo "== 2/4 rpevent logs (public / gm split) =="
gm_list="${ARX1_OUT}/gm-files.txt"
public_list="${ARX1_OUT}/public-files.txt"
(cd "${ARX1_LOG_DIR}" && find . -type f -name "${ARX1_GM_LOG_GLOB}" | sort) > "${gm_list}"
(cd "${ARX1_LOG_DIR}" && find . -type f ! -name "${ARX1_GM_LOG_GLOB}" | sort) > "${public_list}"
gm_count="$(wc -l < "${gm_list}")"
public_count="$(wc -l < "${public_list}")"
echo "   ${public_count} public files, ${gm_count} gm files (glob: ${ARX1_GM_LOG_GLOB})"
if [ "${gm_count}" -eq 0 ]; then
  echo "   WARNING: the GM glob matched NOTHING — if GM logs exist under a" >&2
  echo "   different naming scheme they are about to land in the PUBLIC" >&2
  echo "   tarball. Verify ARX1_GM_LOG_GLOB before trusting this run." >&2
fi
tar -C "${ARX1_LOG_DIR}" -cf - -T "${public_list}" \
  | zstd "${ZSTD_ARGS[@]}" -o "arx1-rpevents-public-${date_tag}.tar.zst" -f
if [ "${gm_count}" -gt 0 ]; then
  tar -C "${ARX1_LOG_DIR}" -cf - -T "${gm_list}" \
    | zstd "${ZSTD_ARGS[@]}" -o "arx1-rpevents-gm-${date_tag}.tar.zst" -f
fi

echo "== 3/4 resurrection kit =="
# Everything needed to make Arx I PLAYABLE again someday, without
# archaeology. The venv is included deliberately: pip freeze alone assumes
# every pinned wheel still exists on PyPI years from now; the venv's actual
# bytes make no such bet. The db and event logs are excluded — they are the
# other artifacts.
kit_extra="${ARX1_OUT}/kit-extra"
rm -rf "${kit_extra}"
mkdir -p "${kit_extra}"
python_bin="python"
if [ -n "${ARX1_VENV}" ] && [ -x "${ARX1_VENV}/bin/python" ]; then
  python_bin="${ARX1_VENV}/bin/python"
  "${ARX1_VENV}/bin/pip" freeze > "${kit_extra}/pip-freeze.txt" || true
fi
"${python_bin}" --version > "${kit_extra}/python-version.txt" 2>&1 || true
crontab -l > "${kit_extra}/crontab.txt" 2>/dev/null || true
uname -a > "${kit_extra}/uname.txt"
# Grab whichever webserver/service configs this box actually has.
for conf_dir in /etc/nginx /etc/apache2 /etc/systemd/system /etc/init.d; do
  if [ -d "${conf_dir}" ]; then
    mkdir -p "${kit_extra}/etc"
    cp -a "${conf_dir}" "${kit_extra}/etc/" 2>/dev/null || true
  fi
done
tar -cf - \
  --exclude="$(basename "${ARX1_DB}")" \
  --exclude='*.db3-journal' \
  -C "$(dirname "${ARX1_GAME_DIR}")" "$(basename "${ARX1_GAME_DIR}")" \
  -C "${ARX1_OUT}" kit-extra \
  | zstd "${ZSTD_ARGS[@]}" -o "arx1-resurrection-kit-${date_tag}.tar.zst" -f
rm -rf "${kit_extra}"

echo "== 4/4 checksums + manifest =="
cat > README.txt <<EOF
Arx I archive freeze — generated ${date_tag} on $(hostname) by arx1-freeze.sh.

Contents:
  arx1-final-${date_tag}.sqlite3.zst        the game database (sqlite,
                                            .backup + VACUUM + integrity_check ok)
  arx1-rpevents-public-${date_tag}.tar.zst  public rpevent logs (${public_count} files)
  arx1-rpevents-gm-${date_tag}.tar.zst      GM/OOC rpevent logs (${gm_count} files) —
                                            PRIVATE, backup-only, never serve
  arx1-resurrection-kit-${date_tag}.tar.zst game dir incl. venv, pip freeze,
                                            python/uname versions, crontab,
                                            /etc service+webserver configs

To decompress (the --long flag is REQUIRED — these are long-window frames):
  zstd -d --long=27 <file>.zst
  zstd -dc --long=27 <file>.tar.zst | tar -xf -

Verify before trusting anything:
  sha256sum -c SHA256SUMS

Log paths inside the rpevent tarballs are relative to: ${ARX1_LOG_DIR}
Game dir was: ${ARX1_GAME_DIR}
GM-vs-public split used the filename glob: ${ARX1_GM_LOG_GLOB}
EOF
rm -f SHA256SUMS
sha256sum ./*.zst README.txt > SHA256SUMS

echo
echo "Freeze complete in ${ARX1_OUT}:"
du -h ./*.zst | sed 's/^/   /'
echo "Next: arx1-upload.sh (see docs/operations/arx1-archival.md)."
