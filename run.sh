#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_root"
venv_python="$project_root/.venv/bin/python"
address="${1:-127.0.0.1:8000}"
version_check='import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 15) else 1)'

if [[ ! -x "$venv_python" ]]; then
    python_command=()
    if command -v py >/dev/null 2>&1 && py -3 -c "$version_check" >/dev/null 2>&1; then
        python_command=(py -3)
    elif command -v python3 >/dev/null 2>&1 && python3 -c "$version_check" >/dev/null 2>&1; then
        python_command=(python3)
    elif command -v python >/dev/null 2>&1 && python -c "$version_check" >/dev/null 2>&1; then
        python_command=(python)
    else
        printf '%s\n' 'Install Python 3.10 through 3.14 from https://www.python.org/downloads/ and run this script again.' >&2
        exit 1
    fi
    printf '%s\n' 'Creating your local Python environment...'
    "${python_command[@]}" -m venv "$project_root/.venv"
fi

if ! "$venv_python" -c "$version_check"; then
    printf '%s\n' 'This .venv needs Python 3.10 through 3.14. Recreate it with a supported Python version.' >&2
    exit 1
fi
printf '%s\n' 'Installing the project dependencies...'
"$venv_python" -m pip install -r "$project_root/requirements.txt"
printf '%s\n' 'Preparing the local database...'
"$venv_python" "$project_root/backend/manage.py" migrate --noinput
printf '\nOpen http://%s/login/ in your browser.\n' "$address"
printf '%s\n' 'Keep this terminal open. Press Ctrl+C to stop the server.'
"$venv_python" "$project_root/backend/manage.py" runserver "$address"
