#!/bin/zsh
set -eu
cd -- "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
    print -u2 'Create .venv and install requirements.txt first; see README.md.'
    exit 1
fi
if ! /usr/bin/curl -fsS --max-time 1 http://127.0.0.1:8894/api/status >/dev/null 2>&1; then
    /bin/launchctl remove local.ps5compute.bridge >/dev/null 2>&1 || true
    /bin/launchctl submit -l local.ps5compute.bridge -o "$PWD/web/server.log" -e "$PWD/web/server.log" -- "$PWD/.venv/bin/python" "$PWD/web/server.py"
    for attempt in {1..50}; do
        /usr/bin/curl -fsS --max-time 1 http://127.0.0.1:8894/api/status >/dev/null 2>&1 && break
        /bin/sleep 0.1
    done
fi
/usr/bin/curl -fsS --max-time 1 http://127.0.0.1:8894/api/status >/dev/null || {
    print -u2 'Bridge did not start; inspect web/server.log.'
    exit 1
}
if [[ "${PS5_DASHBOARD_NO_OPEN:-0}" != 1 ]]; then
    /usr/bin/open http://127.0.0.1:8894
fi
