#!/usr/bin/env bash
set -euo pipefail

# Install systemd units into systemd with the current repo path.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RUNTIME_TEMPLATE="${SCRIPT_DIR}/samba-admin@.service"
RUNTIME_TARGET="/etc/systemd/system/samba-admin@.service"
DEPLOY_TEMPLATE="${SCRIPT_DIR}/samba-admin-deploy@.service"
DEPLOY_TARGET="/etc/systemd/system/samba-admin-deploy@.service"

if [[ ! -f "${RUNTIME_TEMPLATE}" ]]; then
  echo "Template not found: ${RUNTIME_TEMPLATE}" >&2
  exit 1
fi

if [[ ! -f "${DEPLOY_TEMPLATE}" ]]; then
  echo "Template not found: ${DEPLOY_TEMPLATE}" >&2
  exit 1
fi

TMP_FILE="$(mktemp)"
trap 'rm -f "${TMP_FILE}"' EXIT

install_unit() {
  local src="$1"
  local dst="$2"
  sed "s|__PROJECT_DIR__|${PROJECT_DIR}|g" "${src}" > "${TMP_FILE}"
  sudo install -m 0644 "${TMP_FILE}" "${dst}"
}

# Replace placeholder with the absolute repo path and install both units.
install_unit "${RUNTIME_TEMPLATE}" "${RUNTIME_TARGET}"
install_unit "${DEPLOY_TEMPLATE}" "${DEPLOY_TARGET}"
sudo systemctl daemon-reload

echo "Installed: ${RUNTIME_TARGET}"
echo "Installed: ${DEPLOY_TARGET}"
echo "Project directory: ${PROJECT_DIR}"
echo

echo "Usage examples:"
echo "  sudo systemctl start samba-admin@backend"
echo "  sudo systemctl start samba-admin@frontend"
echo "  sudo systemctl start samba-admin@all"
echo "  sudo systemctl stop samba-admin@backend"
echo "  sudo systemctl stop samba-admin@frontend"
echo "  sudo systemctl stop samba-admin@all"
echo "  sudo systemctl status samba-admin@all"
echo "  sudo systemctl enable samba-admin@all"
echo "  sudo systemctl disable samba-admin@all"
echo
echo "Deploy with rebuild examples:"
echo "  sudo systemctl start samba-admin-deploy@backend"
echo "  sudo systemctl start samba-admin-deploy@frontend"
echo "  sudo systemctl start samba-admin-deploy@all"
