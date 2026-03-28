# tests/test_helper/ssh-mock.bash
# Mock ssh — records commands, returns configurable responses
ssh() {
    local args=("$@")
    local remote_cmd="${args[-1]}"
    echo "ssh: $remote_cmd" >> "${BATS_TMPDIR}/ssh-calls.log"

    case "$remote_cmd" in
        "true")
            return 0
            ;;
        "test -f /home/"*"/.cloud-init-complete"|"test -f ~/.cloud-init-complete")
            [[ "${SSH_MOCK_CI_COMPLETE:-true}" == "true" ]] && return 0 || return 1
            ;;
        "command -v "*)
            local tool="${remote_cmd#command -v }"
            if [[ " ${SSH_MOCK_AVAILABLE_TOOLS:-docker node python3} " == *" $tool "* ]]; then
                echo "/usr/bin/$tool"
                return 0
            fi
            return 1
            ;;
        *"cloud-init status"*)
            echo "${SSH_MOCK_CI_STATUS:-status: done}"
            ;;
        "test -d "*)
            return 1
            ;;
        "test -x "*)
            return 1
            ;;
        "git clone "*)
            return 0
            ;;
        *)
            return 0
            ;;
    esac
}
export -f ssh

scp() {
    echo "scp: $*" >> "${BATS_TMPDIR}/scp-calls.log"
    return 0
}
export -f scp
