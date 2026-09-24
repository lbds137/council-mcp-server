#!/bin/bash
# Store a council API key in the encrypted systemd user credential keys.cred.
#
# keys.cred holds every key as NAME=value lines, so council decrypts once at
# startup. Only this user on this machine can decrypt it (host key + TPM2, not
# bound to firmware state, so BIOS updates don't lock it).
#
# Usage:
#   <command that prints the key> | scripts/set-secret.sh NAME
#   scripts/set-secret.sh NAME        # prompts; input is hidden
#
# NAME is the environment variable council reads, e.g. OPENROUTER_API_KEY.
# Setting a NAME that is already stored replaces it; other keys are kept.
# Keys never touch a plaintext file: they pass through shell variables and pipes.

set -euo pipefail

NAME="${1:-}"
if [[ ! "$NAME" =~ ^[A-Z][A-Z0-9_]*$ ]]; then
    echo "Usage: $0 NAME   (NAME like OPENROUTER_API_KEY)" >&2
    exit 1
fi

DIR="${COUNCIL_CREDENTIALS_DIR:-$HOME/.claude-mcp-servers/council/credentials}"
BUNDLE="$DIR/keys.cred"
CRED_NAME="council-keys"

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

# The keys already stored, minus the one being replaced
KEPT=""
if [ -f "$BUNDLE" ]; then
    if ! CURRENT="$(systemd-creds decrypt --user --name="$CRED_NAME" "$BUNDLE" -)"; then
        echo "Could not decrypt $BUNDLE; nothing stored." >&2
        exit 1
    fi
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        [ "${line%%=*}" = "$NAME" ] && continue
        KEPT+="$line"$'\n'
    done < <(printf '%s\n' "$CURRENT")  # a pipe; a here-string may use a temp file
fi
CONTENT="${KEPT}${NAME}=${VALUE}"$'\n'

TMP="$BUNDLE.tmp"
trap 'rm -f "$TMP"' EXIT

printf '%s' "$CONTENT" | systemd-creds encrypt --user --with-key=host+tpm2 --tpm2-pcrs= \
    --name="$CRED_NAME" - "$TMP"

# Only replace keys.cred once the new file decrypts to exactly what was meant
if ! systemd-creds decrypt --user --name="$CRED_NAME" "$TMP" - | cmp -s - <(printf '%s' "$CONTENT"); then
    echo "The new keys.cred did not decrypt back to the same content; nothing stored." >&2
    exit 1
fi
mv "$TMP" "$BUNDLE"
trap - EXIT

STORED="$(printf '%s' "$CONTENT" | cut -d= -f1 | paste -sd, - | sed 's/,/, /g')"
echo "Stored $NAME (${#VALUE} characters) in $BUNDLE; it now holds: $STORED"
