# Shared helpers for the scripts in this folder. Source it, don't run it.

# set_var FILE KEY VALUE — replace KEY=... in FILE, or append it if missing.
set_var() {
  local file="$1" key="$2" val="$3" tmp
  tmp="$(mktemp)"
  if grep -q "^${key}=" "$file"; then
    awk -v k="$key" -v v="$val" 'BEGIN{FS=OFS="="} $1==k {print k "=" v; next} {print}' "$file" > "$tmp"
  else
    cat "$file" > "$tmp"; echo "${key}=${val}" >> "$tmp"
  fi
  cat "$tmp" > "$file"; rm -f "$tmp"
}
