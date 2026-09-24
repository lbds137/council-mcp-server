#!/bin/bash
# Store a council API key as an encrypted systemd user credential.
#
# Only this user on this machine can decrypt it (host key + TPM2, not bound to
# firmware state, so BIOS updates don't lock it). Council decrypts it at startup.
#
# Usage:
#   <command that prints the key> | scripts/set-secret.sh NAME
#   scripts/set-secret.sh NAME        # prompts; input is hidden
#
# NAME is the environment variable council reads, e.g. OPENROUTER_API_KEY.

set -euo pipefail

NAME="${1:-}"
if [[ ! "$NAME" =~ ^[A-Z][A-Z0-9_]*$ ]]; then
    echo "Usage: $0 NAME   (NAME like OPENROUTER_API_KEY)" >&2
    exit 1
fi

DIR="${COUNCIL_CREDENTIALS_DIR:-$HOME/.claude-mcp-servers/council/credentials}"

if [ -t 0 ]; then
    read -rsp "Paste $NAME (input hidden): " VALUE
    echo
else
    VALUE="$(cat)"
fi
VALUE="${VALUE//[$'\t\r\n ']/}"
if [ -z "$VALUE" ]; then
    echo "No value given for $NAME; nothing stored." >&2
    exit 1
fi

umask 077
mkdir -p "$DIR"
chmod 700 "$DIR"
TMP="$DIR/$NAME.cred.tmp"
trap 'rm -f "$TMP"' EXIT

printf '%s' "$VALUE" | systemd-creds encrypt --user --with-key=host+tpm2 --tpm2-pcrs= \
    --name="$NAME" - "$TMP"

# Only replace the stored credential once the new one decrypts to the same value
if ! systemd-creds decrypt --user --name="$NAME" "$TMP" - | cmp -s - <(printf '%s' "$VALUE"); then
    echo "Encrypted $NAME did not decrypt back to the same value; nothing stored." >&2
    exit 1
fi
mv "$TMP" "$DIR/$NAME.cred"
trap - EXIT

echo "Stored $NAME (${#VALUE} characters) in $DIR/$NAME.cred"
