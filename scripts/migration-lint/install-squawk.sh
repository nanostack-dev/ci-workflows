#!/usr/bin/env bash
# Install the pinned squawk release into a directory and print that directory.
#
#   install-squawk.sh <install-dir>
#
# squawk is third-party code that runs in CI, so the release is pinned by
# version AND by the SHA-256 of each platform binary. Bumping it is one commit:
# change SQUAWK_VERSION, then replace the four digests with the `digest` GitHub
# shows for each asset of the release (`gh api repos/sbdchd/squawk/releases/tags/vX.Y.Z`)
# and confirm them against a download. Pick a release that is at least 7 days
# old (infra ADR 0004, decision D5).
#
# Linux uses the static musl builds: they run on any runner image, with no
# dependency on its glibc.
#
# GitHub answers release downloads with transient 5xx, sometimes only to
# anonymous callers (2026-11-09: 45 minutes of 504s). The download is retried
# with backoff, and a token in GH_DOWNLOAD_TOKEN (migration-lint.yml passes the
# workflow token) is sent so it keeps working while anonymous traffic is
# throttled. SQUAWK_DOWNLOAD_URL replaces the release URL for the tests; the
# pinned checksum still applies.
set -euo pipefail

SQUAWK_VERSION='2.68.0' # released 2026-10-08

dest="${1:?usage: install-squawk.sh <install-dir>}"

# A case statement rather than an associative array: macOS ships bash 3.2.
case "$(uname -s)-$(uname -m)" in
  Linux-x86_64)
    platform='linux-musl-x64'
    expected='0baa93efc8577976995faa789449ba0d17b0d24dd8ae35528e79bbb6a7c7dde7'
    ;;
  Linux-aarch64 | Linux-arm64)
    platform='linux-musl-arm64'
    expected='63149a166bdff7fbd23e16c28ea3af44089e623bce8f9665f4c704cea54e0a48'
    ;;
  Darwin-x86_64)
    platform='darwin-x64'
    expected='a4a0194939ed4b5c0b438bba8119f6252fb6d4295e824661962493a79639c3b7'
    ;;
  Darwin-arm64)
    platform='darwin-arm64'
    expected='288f48b86776057038ed86fd3f916f127b107a6c0398f41735bbe7f19b474ca3'
    ;;
  *)
    echo "No squawk build is pinned for $(uname -s) $(uname -m)." >&2
    exit 1
    ;;
esac

sha256_of() {
  if command -v sha256sum > /dev/null 2>&1; then
    sha256sum "$1" | awk '{ print $1 }'
  else
    shasum -a 256 "$1" | awk '{ print $1 }'
  fi
}

# get_once URL OUT TOKEN: one GET; prints the HTTP status, 000 on a network
# error or timeout. curl sends a -H Authorization header only to the host of
# URL, never to the asset CDN GitHub redirects to.
get_once() {
  local status
  if [[ -n "$3" ]]; then
    status="$(curl --silent --show-error --location --connect-timeout 20 --max-time 300 \
      --header "Authorization: Bearer $3" --output "$2" --write-out '%{http_code}' "$1")" || true
  else
    status="$(curl --silent --show-error --location --connect-timeout 20 --max-time 300 \
      --output "$2" --write-out '%{http_code}' "$1")" || true
  fi
  echo "${status:-000}"
}

# download URL OUT: up to 5 attempts, 2/4/8/16 s apart, on a network error, a
# timeout, 408, 429 or 5xx. Any other answer fails at once.
download() {
  local url="$1" out="$2" token="${GH_DOWNLOAD_TOKEN:-}" attempt status delay=2
  for attempt in 1 2 3 4 5; do
    status="$(get_once "$url" "$out" "$token")"
    if [[ -n "$token" && ( "$status" == 401 || "$status" == 403 ) ]]; then
      # A refused token must not block a download that works anonymously.
      echo "GET ${url} refused GH_DOWNLOAD_TOKEN (${status}); continuing anonymously." >&2
      token=''
      status="$(get_once "$url" "$out" '')"
    fi
    case "$status" in
      2??) return 0 ;;
      000 | 408 | 429 | 5??) ;;
      *)
        echo "GET ${url} answered ${status}." >&2
        return 1
        ;;
    esac
    if [[ "$attempt" == 5 ]]; then
      echo "GET ${url} answered ${status} after 5 attempts." >&2
      return 1
    fi
    echo "GET ${url} answered ${status} (attempt ${attempt} of 5); retrying in ${delay}s." >&2
    sleep "$delay"
    delay=$((delay * 2))
  done
}

mkdir -p "$dest"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

url="${SQUAWK_DOWNLOAD_URL:-https://github.com/sbdchd/squawk/releases/download/v${SQUAWK_VERSION}/squawk-${platform}}"
echo "Downloading squawk ${SQUAWK_VERSION} (${platform})" >&2
download "$url" "$tmp/squawk"

actual="$(sha256_of "$tmp/squawk")"
if [[ "$actual" != "$expected" ]]; then
  echo "squawk ${SQUAWK_VERSION} ${platform}: checksum mismatch." >&2
  echo "  expected ${expected}" >&2
  echo "  actual   ${actual}" >&2
  exit 1
fi

install -m 0755 "$tmp/squawk" "$dest/squawk"
"$dest/squawk" --version >&2
echo "$dest"
