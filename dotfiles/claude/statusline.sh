#!/bin/bash
# Make MSYS coreutils (cat/grep/sed/head/tr) resolvable even when this runs from a
# non-login shell spawned by Windows (cmd.exe runs `bash -c`, which does NOT source
# /etc/profile, so /usr/bin is missing → `cat`/`python` not found → empty status line).
# /c/Windows is always on PATH, so the `py` launcher stays available as a fallback.
export PATH="/usr/bin:/bin:$PATH"
input=$(cat)

# Claude Code status line.
# Shows model, project folder, context usage, latest turn tokens, rate-limit room,
# and session cost. Prefer Python for robust JSON parsing; fall back to grep/sed.

PYBIN=""
for _c in python py python3; do command -v "$_c" >/dev/null 2>&1 && { PYBIN="$_c"; break; }; done
if [ -n "$PYBIN" ]; then
  STATUS=$(STATUSLINE_INPUT="$input" "$PYBIN" - <<'PY'
import json
import os
import datetime

_raw = os.environ.get("STATUSLINE_INPUT", "{}") or "{}"
_b = _raw.find("{"); data = json.loads(_raw[_b:] if _b > 0 else _raw)

def dig(obj, *keys, default=None):
    cur = obj
    for key in keys:
        if not isinstance(cur, dict) or key not in cur or cur[key] is None:
            return default
        cur = cur[key]
    return cur

def as_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default

def money(value):
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "0.00"

def compact_tokens(value):
    value = as_int(value)
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 10_000:
        return f"{round(value / 1000):.0f}k"
    if value >= 1_000:
        return f"{value / 1000:.1f}k"
    return str(value)

G = "\033[32m"
Y = "\033[33m"
R = "\033[31m"
N = "\033[0m"

def color_used_pct(value):
    if value >= 50:
        return R
    if value >= 25:
        return Y
    return G

def color_left_pct(value):
    if value < 30:
        return R
    if value < 60:
        return Y
    return G

model = dig(data, "model", "display_name", default="?")
cwd = dig(data, "workspace", "current_dir", default=dig(data, "cwd", default=""))
folder = os.path.basename(str(cwd).rstrip("/\\")) if cwd else "?"

ctx = dig(data, "context_window", default={}) or {}
ctx_pct = as_int(ctx.get("used_percentage"))
ctx_total = as_int(ctx.get("total_input_tokens")) + as_int(ctx.get("total_output_tokens"))
ctx_size = as_int(ctx.get("context_window_size"))

usage = ctx.get("current_usage") or {}
turn_in = (
    as_int(usage.get("input_tokens"))
    + as_int(usage.get("cache_creation_input_tokens"))
    + as_int(usage.get("cache_read_input_tokens"))
)
turn_out = as_int(usage.get("output_tokens"))

five_used = as_int(dig(data, "rate_limits", "five_hour", "used_percentage"))
week_used = as_int(dig(data, "rate_limits", "seven_day", "used_percentage"))
five_left = max(0, 100 - five_used)
week_left = max(0, 100 - week_used)
cost = money(dig(data, "cost", "total_cost_usd", default=0))

def reset_clock(ts):
    # resets_at is Unix epoch seconds; render as local HH:MM (24h). Absent -> "".
    ts = as_int(ts)
    if ts <= 0:
        return ""
    try:
        return "/" + datetime.datetime.fromtimestamp(ts).strftime("%H:%M")
    except (OverflowError, OSError, ValueError):
        return ""

five_reset = reset_clock(dig(data, "rate_limits", "five_hour", "resets_at"))

print(
    f"[{model}] {folder} | "
    f"CTX:{color_used_pct(ctx_pct)}{ctx_pct}%{N} {compact_tokens(ctx_total)}/{compact_tokens(ctx_size)} | "
    f"turn:{compact_tokens(turn_in)}in/{compact_tokens(turn_out)}out | "
    f"5h:{color_left_pct(five_left)}{five_left}%{N}left{five_reset} | "
    f"7d:{color_left_pct(week_left)}{week_left}%{N}left | ${cost}"
)
PY
  )
  if [ -n "$STATUS" ]; then
    echo "$STATUS"
    exit 0
  fi
fi

# Fallback parser for machines without Python. Less precise, but keeps the line alive.
get_val() {
  echo "$input" | grep -o "\"$1\"[[:space:]]*:[[:space:]]*[^,}]*" | head -1 | sed 's/.*:[[:space:]]*//' | tr -d '" '
}

MODEL=$(get_val "display_name")
CTX_USED=$(get_val "used_percentage")
FIVE_HR=$(echo "$input" | grep -o '"five_hour"[^}]*' | grep -o '"used_percentage"[[:space:]]*:[[:space:]]*[0-9.]*' | sed 's/.*:[[:space:]]*//')
SEVEN_DAY=$(echo "$input" | grep -o '"seven_day"[^}]*' | grep -o '"used_percentage"[[:space:]]*:[[:space:]]*[0-9.]*' | sed 's/.*:[[:space:]]*//')
COST=$(get_val "total_cost_usd")

MODEL=${MODEL:-"?"}
CTX_USED=${CTX_USED%%.*}
CTX_USED=${CTX_USED:-0}
FIVE_HR=${FIVE_HR%%.*}
FIVE_HR=${FIVE_HR:-0}
SEVEN_DAY=${SEVEN_DAY%%.*}
SEVEN_DAY=${SEVEN_DAY:-0}
FIVE_LEFT=$((100 - FIVE_HR))
WEEK_LEFT=$((100 - SEVEN_DAY))
COST=${COST:-0}

G=$'\033[32m'
Y=$'\033[33m'
R=$'\033[31m'
N=$'\033[0m'

if   [ "$CTX_USED" -ge 50 ]; then CTX_COLOR=$R
elif [ "$CTX_USED" -ge 25 ]; then CTX_COLOR=$Y
else                              CTX_COLOR=$G
fi

if   [ "$FIVE_LEFT" -lt 30 ]; then FIVE_COLOR=$R
elif [ "$FIVE_LEFT" -lt 60 ]; then FIVE_COLOR=$Y
else                               FIVE_COLOR=$G
fi

if   [ "$WEEK_LEFT" -lt 30 ]; then WEEK_COLOR=$R
elif [ "$WEEK_LEFT" -lt 60 ]; then WEEK_COLOR=$Y
else                               WEEK_COLOR=$G
fi

printf "[%s] CTX:%s%s%%%s | 5h:%s%s%%%sleft | 7d:%s%s%%%sleft | \$%s" \
  "$MODEL" \
  "$CTX_COLOR" "$CTX_USED" "$N" \
  "$FIVE_COLOR" "$FIVE_LEFT" "$N" \
  "$WEEK_COLOR" "$WEEK_LEFT" "$N" \
  "$COST"
