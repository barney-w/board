#!/usr/bin/env bash
# UI abstraction layer — uses gum if available, falls back to plain bash

USE_GUM=false
if command -v gum &>/dev/null; then
    USE_GUM=true
fi

# ── Brand Colors ──
BOARD_COLOR="#0ea5e9"  # Sky-500

if $USE_GUM; then
    export GUM_CHOOSE_CURSOR_FOREGROUND="$BOARD_COLOR"
    export GUM_CHOOSE_SELECTED_FOREGROUND="$BOARD_COLOR"
    export GUM_SPIN_SPINNER_FOREGROUND="$BOARD_COLOR"
    export GUM_INPUT_CURSOR_FOREGROUND="$BOARD_COLOR"
    export GUM_INPUT_PROMPT_FOREGROUND="$BOARD_COLOR"
    export GUM_CONFIRM_SELECTED_FOREGROUND="$BOARD_COLOR"
fi

# ── Colors (fallback mode) ──

_green=$'\033[32m'
_red=$'\033[31m'
_yellow=$'\033[33m'
_blue=$'\033[34m'
_cyan=$'\033[36m'
_sky=$'\033[38;2;14;165;233m'  # Sky-500 #0ea5e9
_bold=$'\033[1m'
_dim=$'\033[2m'
_reset=$'\033[0m'

# ── Display ──

ui_header() {
    local text="$1"
    if $USE_GUM; then
        echo ""
        gum style --border rounded --padding "0 2" --border-foreground "$BOARD_COLOR" "$text"
    else
        echo ""
        local width=${#text}
        local border
        border=$(printf '%.0s─' $(seq 1 $((width + 4))))
        echo "${_sky}╭${border}╮${_reset}"
        echo "${_sky}│${_reset}  ${_bold}${text}${_reset}  ${_sky}│${_reset}"
        echo "${_sky}╰${border}╯${_reset}"
    fi
    echo ""
}

ui_banner() {
    if $USE_GUM; then
        gum style --border double --padding "1 3" --border-foreground "$BOARD_COLOR" \
            --bold --foreground "$BOARD_COLOR" "$1" "" "$2"
    else
        echo ""
        echo "${_bold}${_sky}$1${_reset}"
        echo "${_dim}$2${_reset}"
        echo ""
    fi
    echo ""
}

ui_step() {
    local step="$1" total="$2" label="$3"
    if $USE_GUM; then
        gum style --foreground "$BOARD_COLOR" --bold "[$step/$total] $label"
    else
        echo "${_sky}${_bold}[$step/$total]${_reset} ${_bold}$label${_reset}"
    fi
    echo ""
}

ui_success() {
    if $USE_GUM; then
        gum style --foreground 10 "  ✓ $1"
    else
        echo "  ${_green}✓${_reset} $1"
    fi
}

ui_error() {
    if $USE_GUM; then
        gum style --foreground 9 "  ✗ $1" >&2
    else
        echo "  ${_red}✗${_reset} $1" >&2
    fi
}

ui_warn() {
    if $USE_GUM; then
        gum style --foreground 11 "  ! $1"
    else
        echo "  ${_yellow}!${_reset} $1"
    fi
}

ui_info() {
    if $USE_GUM; then
        gum style --foreground 245 "  $1"
    else
        echo "  ${_dim}$1${_reset}"
    fi
}

ui_divider() {
    if $USE_GUM; then
        gum style --foreground 240 "$(printf '%.0s─' {1..50})"
    else
        echo "${_dim}$(printf '%.0s─' {1..50})${_reset}"
    fi
}

# ── Input ──

ui_input() {
    local prompt="$1"
    local default="${2:-}"
    if $USE_GUM; then
        local result rc=0
        result=$(gum input --prompt "${prompt}: " --placeholder "$default" --value "$default") || rc=$?
        if (( rc != 0 )); then kill -INT $$ 2>/dev/null; return 130; fi
        echo "$result"
    else
        local value
        if [[ -n "$default" ]]; then
            read -rp "${prompt} [${default}]: " value </dev/tty
            echo "${value:-$default}"
        else
            read -rp "${prompt}: " value </dev/tty
            echo "$value"
        fi
    fi
}

ui_input_validated() {
    local prompt="$1"
    local default="${2:-}"
    local regex="$3"
    local error_msg="$4"
    while true; do
        local value rc=0
        value=$(ui_input "$prompt" "$default") || rc=$?
        if (( rc != 0 )); then return "$rc"; fi
        if [[ "$value" =~ $regex ]]; then
            echo "$value"
            return 0
        fi
        ui_error "$error_msg" >&2
    done
}

ui_input_secret() {
    local prompt="$1"
    if $USE_GUM; then
        local result rc=0
        result=$(gum input --password --prompt "${prompt}: ") || rc=$?
        if (( rc != 0 )); then kill -INT $$ 2>/dev/null; return 130; fi
        echo "$result"
    else
        local value
        read -s -rp "${prompt}: " value </dev/tty
        echo "" >&2
        echo "$value"
    fi
}

ui_choose() {
    local prompt="$1"
    shift
    if $USE_GUM; then
        local result rc=0
        result=$(gum choose --header "$prompt" -- "$@") || rc=$?
        if (( rc != 0 )); then kill -INT $$ 2>/dev/null; return 130; fi
        echo "$result"
    else
        echo "$prompt" >&2
        local i=1
        for option in "$@"; do
            echo "  ${_cyan}${i})${_reset} $option" >&2
            ((i++))
        done
        local choice
        while true; do
            read -rp "  Choice [1-$#]: " choice </dev/tty
            if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= $# )); then
                local idx=0
                for option in "$@"; do
                    ((idx++))
                    if (( idx == choice )); then
                        echo "$option"
                        return 0
                    fi
                done
            fi
            echo "  Please enter a number between 1 and $#" >&2
        done
    fi
}

ui_checklist() {
    local prompt="$1"
    shift
    local selected=""
    if [[ "${1:-}" == --selected=* ]]; then
        selected="${1#--selected=}"
        shift
    fi
    if $USE_GUM; then
        local result rc=0
        local -a gum_args=(--no-limit --header "$prompt  (Space to toggle, Enter to confirm)")
        [[ -n "$selected" ]] && gum_args+=(--selected "$selected")
        result=$(gum choose "${gum_args[@]}" -- "$@") || rc=$?
        if (( rc != 0 )); then kill -INT $$ 2>/dev/null; return 130; fi
        echo "$result"
    else
        echo "$prompt" >&2
        local i=1
        for option in "$@"; do
            echo "  ${_cyan}${i})${_reset} $option" >&2
            ((i++))
        done
        echo "" >&2
        # Build default numbers from --selected items
        local default_nums=""
        if [[ -n "$selected" ]]; then
            local idx=0
            for option in "$@"; do
                ((idx++))
                if [[ "$selected" == "*" ]] || [[ ",$selected," == *",$option,"* ]]; then
                    default_nums="${default_nums:+$default_nums,}$idx"
                fi
            done
        fi
        local choices
        if [[ -n "$default_nums" ]]; then
            read -rp "  Select (comma-separated numbers) [$default_nums]: " choices </dev/tty
            [[ -z "$choices" ]] && choices="$default_nums"
        else
            read -rp "  Select (comma-separated numbers, e.g. 1,2): " choices </dev/tty
        fi
        IFS=',' read -ra nums <<< "$choices"
        for num in "${nums[@]}"; do
            num=$(echo "$num" | tr -d ' ')
            if [[ "$num" =~ ^[0-9]+$ ]] && (( num >= 1 && num <= $# )); then
                local idx=0
                for option in "$@"; do
                    ((idx++))
                    if (( idx == num )); then
                        echo "$option"
                    fi
                done
            fi
        done
    fi
}

ui_confirm() {
    local prompt="$1"
    local default="${2:-yes}"
    if $USE_GUM; then
        local rc=0
        if [[ "$default" == "no" ]]; then
            gum confirm --default=No "$prompt" || rc=$?
        else
            gum confirm "$prompt" || rc=$?
        fi
        # gum confirm returns 1 for "No" and 130 for Ctrl+C
        if (( rc == 130 )); then kill -INT $$ 2>/dev/null; return 130; fi
        return $rc
    else
        local yn
        if [[ "$default" == "no" ]]; then
            read -rp "$prompt (y/N): " yn </dev/tty
            [[ "$yn" =~ ^[Yy] ]]
        else
            read -rp "$prompt (Y/n): " yn </dev/tty
            [[ ! "$yn" =~ ^[Nn] ]]
        fi
    fi
}

# ── Progress ──

ui_spin() {
    local title="$1"
    shift
    if $USE_GUM; then
        gum spin --spinner dot --title "$title" -- "$@"
    else
        echo -n "  $title... "
        if "$@" >/dev/null 2>&1; then
            echo "done"
        else
            echo "failed"
            return 1
        fi
    fi
}

ui_spin_visible() {
    local title="$1"
    shift
    if $USE_GUM; then
        gum spin --spinner dot --title "$title" --show-output -- "$@"
    else
        echo "  $title..."
        "$@"
    fi
}

# ── Summary box ──

ui_summary_box() {
    local title="$1"
    shift
    # Remaining args are "key: value" lines
    if $USE_GUM; then
        local body=""
        for line in "$@"; do
            if [[ -n "$body" ]]; then
                body="${body}"$'\n'"  ${line}"
            else
                body="  ${line}"
            fi
        done
        gum style --border rounded --padding "0 2" --border-foreground "$BOARD_COLOR" \
            --bold "$title" "" "$body"
    else
        local max_width=0
        for line in "$@"; do
            (( ${#line} > max_width )) && max_width=${#line}
        done
        (( ${#title} > max_width )) && max_width=${#title}
        local border
        border=$(printf '%.0s─' $(seq 1 $((max_width + 6))))

        echo "${_sky}╭${border}╮${_reset}"
        printf "${_sky}│${_reset}  ${_bold}%-*s${_reset}    ${_sky}│${_reset}\n" "$max_width" "$title"
        echo "${_sky}│${_reset}$(printf '%.0s ' $(seq 1 $((max_width + 6))))${_sky}│${_reset}"
        for line in "$@"; do
            printf "${_sky}│${_reset}  %-*s    ${_sky}│${_reset}\n" "$max_width" "$line"
        done
        echo "${_sky}╰${border}╯${_reset}"
    fi
    echo ""
}

# ── ASCII Banner ──

ui_ascii_banner() {
    if $USE_GUM; then
        gum style --border double --padding "1 3" --border-foreground "$BOARD_COLOR" \
            --bold --foreground "$BOARD_COLOR" \
            "██████╗  ██████╗  █████╗ ██████╗ ██████╗ " \
            "██╔══██╗██╔═══██╗██╔══██╗██╔══██╗██╔══██╗" \
            "██████╔╝██║   ██║███████║██████╔╝██║  ██║" \
            "██╔══██╗██║   ██║██╔══██║██╔══██╗██║  ██║" \
            "██████╔╝╚██████╔╝██║  ██║██║  ██║██████╔╝" \
            "╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ " \
            "" \
            "  $1"
    else
        echo ""
        echo "${_bold}${_sky}  BOARD${_reset}"
        echo "${_dim}  $1${_reset}"
        echo ""
    fi
    echo ""
}

# ── Completion Box ──

ui_completion_box() {
    local title="$1"
    shift
    if $USE_GUM; then
        local body=""
        for line in "$@"; do
            body="${body:+${body}$'\n'}  ${line}"
        done
        gum style --border double --padding "1 3" --border-foreground "$BOARD_COLOR" \
            --bold "$title" "" "$body"
    else
        ui_summary_box "$title" "$@"
    fi
    echo ""
}

# ── Warning Summary ──

ui_warn_summary() {
    local title="$1"
    shift
    (( $# == 0 )) && return 0
    if $USE_GUM; then
        local body=""
        for line in "$@"; do
            body="${body:+${body}$'\n'}  ! ${line}"
        done
        gum style --border rounded --padding "0 2" --border-foreground 11 \
            "$title ($#)" "" "$body"
    else
        echo ""
        echo "  ${_yellow}${_bold}$title ($#)${_reset}"
        for line in "$@"; do
            echo "  ${_yellow}!${_reset} $line"
        done
    fi
    echo ""
}

# ── Board Pass ──

ui_boarding_pass() {
    local name="$1"
    local region="$2"
    local region_short="$3"
    local environment="$4"
    local hostname="$5"
    local auth_method="$6"
    local issued="$7"
    local valid_until="$8"
    local output_file="$9"

    local zone
    zone=$(echo "$region_short" | tr '[:lower:]' '[:upper:]')

    # Format dates for display (strip time portion)
    local issued_short="${issued%%T*}"
    local expiry_short="${valid_until%%T*}"

    # Initials for badge avatar
    local initials
    initials=$(echo "${name:0:2}" | tr '[:lower:]' '[:upper:]')

    # Truncate hostname if needed
    local host_display="$hostname"
    if (( ${#host_display} > 42 )); then
        host_display="${host_display:0:39}..."
    fi

    # Generate a decorative barcode from the name
    local barcode=""
    local bar_chars=("┃" "│" "┃" "│" "║" "│" "┃" "│")
    local i
    for i in $(seq 1 48); do
        barcode="${barcode}${bar_chars[$(( (i * ${#name}) % ${#bar_chars[@]} ))]}"
    done

    if $USE_GUM; then
        local perf="· · · · · · · · · · · · · · · · · · · · · · · · · ·"
        gum style --border double --padding "1 2" --border-foreground "$BOARD_COLOR" \
            "$(gum style --foreground "$BOARD_COLOR" --bold -- '  ◆  B O A R D   P A S S')" \
            "$(gum style --foreground 245 -- '  ACCESS CREDENTIAL')" \
            "" \
            "$(gum style --bold -- "  [$initials]  $name")" \
            "$(gum style --foreground 245 -- "       $environment environment")" \
            "" \
            "$(printf '  %-20s  %-18s  %s' 'REGION' 'AUTH METHOD' 'ZONE')" \
            "$(gum style --bold -- "$(printf '  %-20s  %-18s  %s' "$region" "$auth_method" "$zone")")" \
            "" \
            "$(printf '  HOST')" \
            "$(gum style --bold --foreground 245 -- "  $host_display")" \
            "" \
            "  $(gum style --foreground 245 -- "$perf")" \
            "" \
            "$(printf '  %-20s  %-18s  %s' 'ISSUED' 'EXPIRES' 'FILE')" \
            "$(gum style --bold -- "$(printf '  %-20s  %-18s  %s' "$issued_short" "$expiry_short" "$output_file")")" \
            "" \
            "  $(gum style --foreground "$BOARD_COLOR" -- "$barcode")" \
            "  $(gum style --foreground 245 -- "$output_file")"
    else
        local w=60
        local border_h
        border_h=$(printf '%.0s═' $(seq 1 $w))
        local perf
        perf=$(printf '%.0s· ' $(seq 1 $(( w / 2 - 2 ))))

        echo ""
        echo "${_sky}╔${border_h}╗${_reset}"
        echo "${_sky}║${_reset}                                                            ${_sky}║${_reset}"
        printf "${_sky}║${_reset}  ${_bold}${_sky}◆  B O A R D   P A S S${_reset}%*s${_sky}║${_reset}\n" $(( w - 24 )) ""
        printf "${_sky}║${_reset}  ${_dim}%-56s${_reset}  ${_sky}║${_reset}\n" "ACCESS CREDENTIAL"
        echo "${_sky}║${_reset}                                                            ${_sky}║${_reset}"
        echo "${_sky}╠${border_h}╣${_reset}"
        echo "${_sky}║${_reset}                                                            ${_sky}║${_reset}"

        # Identity: avatar + name
        printf "${_sky}║${_reset}  ${_sky}[${_bold}${initials}${_reset}${_sky}]${_reset}  ${_bold}%-50s${_reset}  ${_sky}║${_reset}\n" "$name"
        printf "${_sky}║${_reset}       ${_dim}%-51s${_reset}  ${_sky}║${_reset}\n" "$environment environment"
        echo "${_sky}║${_reset}                                                            ${_sky}║${_reset}"

        # Row 1: Region / Auth / Zone
        printf "${_sky}║${_reset}  ${_dim}%-18s  %-22s  %-12s${_reset}  ${_sky}║${_reset}\n" "REGION" "AUTH METHOD" "ZONE"
        printf "${_sky}║${_reset}  ${_bold}%-18s${_reset}  ${_bold}%-22s${_reset}  ${_bold}${_sky}%-12s${_reset}  ${_sky}║${_reset}\n" "$region" "$auth_method" "$zone"
        echo "${_sky}║${_reset}                                                            ${_sky}║${_reset}"

        # Row 2: Host (full width)
        printf "${_sky}║${_reset}  ${_dim}%-56s${_reset}  ${_sky}║${_reset}\n" "HOST"
        printf "${_sky}║${_reset}  ${_bold}%-56s${_reset}  ${_sky}║${_reset}\n" "$host_display"
        echo "${_sky}║${_reset}                                                            ${_sky}║${_reset}"

        # Perforation
        printf "${_sky}║${_reset}  ${_dim}%.56s${_reset}  ${_sky}║${_reset}\n" "$perf"
        echo "${_sky}║${_reset}                                                            ${_sky}║${_reset}"

        # Row 3: Issued / Expires / File
        printf "${_sky}║${_reset}  ${_dim}%-18s  %-22s  %-12s${_reset}  ${_sky}║${_reset}\n" "ISSUED" "EXPIRES" "FILE"
        printf "${_sky}║${_reset}  ${_bold}%-18s${_reset}  ${_bold}%-22s${_reset}  ${_bold}%-12s${_reset}  ${_sky}║${_reset}\n" "$issued_short" "$expiry_short" "$output_file"
        echo "${_sky}║${_reset}                                                            ${_sky}║${_reset}"

        # Barcode
        printf "${_sky}║${_reset}  ${_sky}%-56s${_reset}  ${_sky}║${_reset}\n" "$barcode"
        printf "${_sky}║${_reset}  ${_dim}%-56s${_reset}  ${_sky}║${_reset}\n" "$output_file"
        echo "${_sky}║${_reset}                                                            ${_sky}║${_reset}"
        echo "${_sky}╚${border_h}╝${_reset}"
    fi
    echo ""
}

# ── Sound ──

ui_play_sound() {
    if command -v afplay &>/dev/null; then
        afplay /System/Library/Sounds/Hero.aiff &
    elif command -v paplay &>/dev/null; then
        paplay /usr/share/sounds/freedesktop/stereo/complete.oga &
    fi
    true
}

# ── Webhook ──

ui_webhook() {
    local message="$1"
    if [[ -n "${BOARD_WEBHOOK_URL:-}" ]]; then
        curl -sf -X POST "$BOARD_WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -d "{\"text\":\"$message\"}" \
            &>/dev/null || true
    fi
}
