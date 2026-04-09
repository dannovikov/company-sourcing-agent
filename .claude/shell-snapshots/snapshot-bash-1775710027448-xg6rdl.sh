# Snapshot file
# Unset all aliases to avoid conflicts with functions
unalias -a 2>/dev/null || true
shopt -s expand_aliases
# Check for rg availability
if ! (unalias rg 2>/dev/null; command -v rg) >/dev/null 2>&1; then
  function rg {
  if [[ -n $ZSH_VERSION ]]; then
    ARGV0=rg /app/.venv/lib/python3.11/site-packages/claude_agent_sdk/_bundled/claude "$@"
  elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
    ARGV0=rg /app/.venv/lib/python3.11/site-packages/claude_agent_sdk/_bundled/claude "$@"
  elif [[ $BASHPID != $$ ]]; then
    exec -a rg /app/.venv/lib/python3.11/site-packages/claude_agent_sdk/_bundled/claude "$@"
  else
    (exec -a rg /app/.venv/lib/python3.11/site-packages/claude_agent_sdk/_bundled/claude "$@")
  fi
}
fi
export PATH=/home/worker/.bun/bin\:/home/worker/.fly/bin\:/usr/local/sbin\:/usr/local/bin\:/usr/sbin\:/usr/bin\:/sbin\:/bin
