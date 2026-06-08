#!/bin/bash
input=$(cat)

# Parse JSON without jq using grep/sed
get_val() {
  echo "$input" | grep -o "\"$1\"[[:space:]]*:[[:space:]]*[^,}]*" | head -1 | sed 's/.*:[[:space:]]*//' | tr -d '" '
}

MODEL=$(get_val "display_name")
CTX_USED=$(get_val "used_percentage")
FIVE_HR=$(echo "$input" | grep -o '"five_hour"[^}]*' | grep -o '"used_percentage"[[:space:]]*:[[:space:]]*[0-9.]*' | sed 's/.*:[[:space:]]*//')
SEVEN_DAY=$(echo "$input" | grep -o '"seven_day"[^}]*' | grep -o '"used_percentage"[[:space:]]*:[[:space:]]*[0-9.]*' | sed 's/.*:[[:space:]]*//')
COST=$(get_val "total_cost_usd")

# Default values
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

# ANSI colors
G=$'\033[32m'  # green
Y=$'\033[33m'  # yellow
R=$'\033[31m'  # red
N=$'\033[0m'   # reset

# CTX used%: high = bad (0~25 green, 25~50 yellow, 50+ red)
if   [ "$CTX_USED" -ge 50 ]; then CTX_COLOR=$R
elif [ "$CTX_USED" -ge 25 ]; then CTX_COLOR=$Y
else                              CTX_COLOR=$G
fi

# 5h left: low = bad (60+ green, 30~60 yellow, <30 red)
if   [ "$FIVE_LEFT" -lt 30 ]; then FIVE_COLOR=$R
elif [ "$FIVE_LEFT" -lt 60 ]; then FIVE_COLOR=$Y
else                               FIVE_COLOR=$G
fi

# 7d left: same scheme as 5h
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
