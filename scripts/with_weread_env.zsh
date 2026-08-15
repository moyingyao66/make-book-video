#!/bin/zsh
set -euo pipefail

# Inject the WeRead API key into one child process without writing the secret
# to a project file, shell profile, command line, or report.

readonly PRIMARY_SERVICE="book-sales-video.WEREAD_API_KEY"
readonly FALLBACK_SERVICE="codex.book-sales-video.WEREAD_API_KEY"

if [[ -z "${WEREAD_API_KEY:-}" ]]; then
  if [[ "$(uname -s)" != "Darwin" ]] || [[ ! -x /usr/bin/security ]]; then
    print -u2 "WEREAD_API_KEY is absent and macOS Keychain is unavailable"
    exit 2
  fi

  readonly keychain_account="$(/usr/bin/id -un)"
  weread_key=""

  for keychain_service in "$PRIMARY_SERVICE" "$FALLBACK_SERVICE"; do
    if weread_key="$(/usr/bin/security find-generic-password \
      -a "$keychain_account" \
      -s "$keychain_service" \
      -w 2>/dev/null)"; then
      break
    fi
    weread_key=""
  done

  if [[ -z "$weread_key" ]]; then
    print -u2 "No WeRead API key was found in the approved Keychain services"
    exit 2
  fi

  export WEREAD_API_KEY="$weread_key"
  unset weread_key
fi

if [[ "$WEREAD_API_KEY" != wrk-* ]]; then
  print -u2 "The configured WeRead credential has an unexpected format"
  exit 2
fi

if [[ $# -eq 1 && "$1" == "--check" ]]; then
  print "WEREAD_API_KEY=available"
  exit 0
fi

if [[ $# -eq 0 ]]; then
  print -u2 "usage: with_weread_env.zsh --check | <command> [args ...]"
  exit 2
fi

exec "$@"
