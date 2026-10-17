#!/bin/sh
# Runs `codelabgen hook <event>` with the hook input on stdin.
# Uses codelabgen from PATH, else the plugin's own .venv; does nothing if neither exists,
# so a missing CLI never breaks the session.
here=$(cd "$(dirname "$0")/.." && pwd)
if command -v codelabgen >/dev/null 2>&1; then
  exec codelabgen hook "$@"
elif [ -x "$here/.venv/bin/codelabgen" ]; then
  exec "$here/.venv/bin/codelabgen" hook "$@"
fi
cat >/dev/null
exit 0
