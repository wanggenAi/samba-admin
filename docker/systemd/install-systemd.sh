#!/usr/bin/env bash
set -euo pipefail

# Install samba-admin@.service into systemd with the current repo path.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TEMPLATE_FILE="${SCRIPT_DIR}/samba-admin@.service"
TARGET_FILE="/etc/systemd/system/samba-admin@.service"

if [[ ! -f "${TEMPLATE_FILE}" ]]; then
  echo "Template not found: ${TEMPLATE_FILE}" >&2
  exit 1
fi

TMP_FILE="$(mktemp)"
trap 'rm -f "${TMP_FILE}"' EXIT

# Replace placeholder with the absolute repo path.
sed "s|__PROJECT_DIR__|${PROJECT_DIR}|g" "${TEMPLATE_FILE}" > "${TMP_FILE}"

sudo install -m 0644 "${TMP_FILE}" "${TARGET_FILE}"
sudo systemctl daemon-reload

echo "Installed: ${TARGET_FILE}"
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
