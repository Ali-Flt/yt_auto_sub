#!/usr/bin/env bash
# docker pull that survives a flaky connection: blobs resume where they stopped, and a re-run picks up again.
# Usage: ./pull-image.sh ghcr.io/ggml-org/llama.cpp:server-cuda12-b11561
set -euo pipefail

ref=${1:?usage: $0 registry/repo:tag}
name=${ref%:*} tag=${ref##*:}
first=${name%%/*}
if [[ $name == */* && $first == *[.:]* ]]; then
  registry=$first repo=${name#*/}
else
  registry=registry-1.docker.io repo=$name
  [[ $repo == */* ]] || repo=library/$repo
fi
dir=${XDG_CACHE_HOME:-$HOME/.cache}/pull-image/${ref//[\/:]/_}
mkdir -p "$dir"

token() {
  local challenge realm service
  challenge=$(curl -sS --retry 10 --retry-all-errors -o /dev/null -D - "https://$registry/v2/" | grep -i '^www-authenticate:')
  realm=$(sed -E 's/.*realm="([^"]+)".*/\1/' <<<"$challenge")
  service=$(sed -E 's/.*service="([^"]+)".*/\1/' <<<"$challenge")
  curl -fsS --retry 10 --retry-all-errors "$realm?service=$service&scope=repository:$repo:pull" | jq -r '.token // .access_token'
}

manifest() {
  curl -fsSL --retry 10 --retry-all-errors -o "$dir/manifest" -H "Authorization: Bearer $(token)" \
    -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json' \
    "https://$registry/v2/$repo/manifests/$1"
}

manifest "$tag"
platform=$(jq -r 'first(.manifests[]? | select(.platform.os == "linux" and .platform.architecture == "amd64") | .digest) // empty' "$dir/manifest")
[[ -z $platform ]] || manifest "$platform"

mapfile -t blobs < <(jq -r '.config, .layers[] | "\(.digest) \(.size)"' "$dir/manifest")
for blob in "${blobs[@]}"; do
  read -r digest size <<<"$blob"
  file=$dir/${digest#sha256:}
  [[ -f $file ]] || echo "$digest ($((size / 1048576)) MB)"
  until [[ -f $file ]]; do
    while (($(stat -c %s "$file.part" 2>/dev/null || echo 0) < size)); do
      curl -fL -C - --connect-timeout 20 --speed-limit 1024 --speed-time 60 -o "$file.part" \
        -H "Authorization: Bearer $(token)" "https://$registry/v2/$repo/blobs/$digest" ||
        { echo "interrupted, resuming in 5 s"; sleep 5; }
    done
    if sha256sum -c --status <<<"${digest#sha256:}  $file.part"; then
      mv "$file.part" "$file"
    else
      echo "checksum mismatch, downloading $digest again"
      rm "$file.part"
    fi
  done
done

jq --arg ref "$ref" '[{Config: (.config.digest | ltrimstr("sha256:")), RepoTags: [$ref], Layers: [.layers[].digest | ltrimstr("sha256:")]}]' \
  "$dir/manifest" >"$dir/manifest.json"
mapfile -t files < <(jq -r '.config.digest, .layers[].digest | ltrimstr("sha256:")' "$dir/manifest")
tar -C "$dir" -cf - manifest.json "${files[@]}" | docker load
rm -rf "$dir"
