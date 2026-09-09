#!/usr/bin/env bash
set -euo pipefail
APP=jdsl

MUTED='\033[0;2m'
RED='\033[0;31m'
ORANGE='\033[38;5;214m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

usage() {
    cat <<EOF
jdsl Installer

Usage: install.sh [options]

Options:
    -h, --help              Display this help message
    -v, --version <version> Install a specific version (e.g., 0.1.0)
    -b, --binary <path>     Install from a local binary instead of downloading
        --no-modify-path    Don't modify shell config files (.zshrc, .bashrc, etc.)

Examples:
    curl -fsSL https://raw.githubusercontent.com/marsrover/jdsl-py/harness/install.sh | bash
    curl -fsSL https://raw.githubusercontent.com/marsrover/jdsl-py/harness/install.sh | bash -s -- --version 0.1.0
    ./install --binary /path/to/jdsl
EOF
}

requested_version=${VERSION:-}
no_modify_path=false
binary_path=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        -v|--version)
            if [[ -n "${2:-}" ]]; then
                requested_version="$2"
                shift 2
            else
                echo -e "${RED}Error: --version requires a version argument${NC}"
                exit 1
            fi
            ;;
        -b|--binary)
            if [[ -n "${2:-}" ]]; then
                binary_path="$2"
                shift 2
            else
                echo -e "${RED}Error: --binary requires a path argument${NC}"
                exit 1
            fi
            ;;
        --no-modify-path)
            no_modify_path=true
            shift
            ;;
        *)
            echo -e "${ORANGE}Warning: Unknown option '$1'${NC}" >&2
            shift
            ;;
    esac
done

INSTALL_DIR=$HOME/.jdsl/bin
mkdir -p "$INSTALL_DIR"

if [ -n "$binary_path" ]; then
    if [ ! -f "$binary_path" ]; then
        echo -e "${RED}Error: Binary not found at ${binary_path}${NC}"
        exit 1
    fi
    specific_version="local"
else
    # Detect OS / Arch
    raw_os=$(uname -s)
    os=$(echo "$raw_os" | tr '[:upper:]' '[:lower:]')
    case "$raw_os" in
      Darwin*) os="darwin" ;;
      Linux*) os="linux" ;;
      MINGW*|MSYS*|CYGWIN*) os="windows" ;;
    esac

    arch=$(uname -m)
    if [[ "$arch" == "aarch64" ]]; then
      arch="arm64"
    fi
    if [[ "$arch" == "x86_64" ]]; then
      arch="x64"
    fi

    combo="$os-$arch"
    case "$combo" in
      linux-x64|linux-arm64|darwin-x64|darwin-arm64|windows-x64)
        ;;
      *)
        echo -e "${RED}Unsupported OS/Arch: $os/$arch${NC}"
        exit 1
        ;;
    esac

    if [ -z "$requested_version" ]; then
        url="https://cantorindustries.com/jdsl-py/jdsl-$os-$arch.tar.gz"
        specific_version=$(curl -s https://api.github.com/repos/marsrover/jdsl-py/releases/latest | sed -n 's/.*"tag_name": *"v\([^"]*\)".*/\1/p' || echo "unknown")
    else
        requested_version="${requested_version#v}"
        url="https://cantorindustries.com/jdsl-py/jdsl-$os-$arch.tar.gz"
        specific_version=$requested_version
    fi
fi

check_version() {
    if command -v jdsl >/dev/null 2>&1; then
        installed_version=$(jdsl --version 2>/dev/null || echo "")
        if [[ "$installed_version" == "$specific_version" ]] || [[ "$specific_version" == "unknown" ]]; then
            : # continue
        else
            echo -e "${MUTED}Installed version: ${installed_version}${NC}"
        fi
    fi
}

if [ -n "$binary_path" ]; then
    echo -e "${ORANGE}Installing jdsl from local binary...${NC}"
    cp "$binary_path" "${INSTALL_DIR}/jdsl"
    chmod 755 "${INSTALL_DIR}/jdsl"
else
    echo -e "${ORANGE}Installing jdsl version: $specific_version${NC}"
    tmp_dir="${TMPDIR:-/tmp}/jdsl_install_$$"
    mkdir -p "$tmp_dir"
    curl -# -L -o "$tmp_dir/jdsl.tar.gz" "$url"
    tar -xzf "$tmp_dir/jdsl.tar.gz" -C "$tmp_dir"
    if [ -f "$tmp_dir/bin/jdsl" ]; then
        # Binary package with lib/ source: install binary and source dirs
        mkdir -p "$INSTALL_DIR"
        mv "$tmp_dir/bin/jdsl" "$INSTALL_DIR"
        chmod 755 "${INSTALL_DIR}/jdsl"
        if [ -d "$tmp_dir/lib" ]; then
            mkdir -p "${INSTALL_DIR}/../lib"
            if [ -d "$tmp_dir/lib/jdsl" ]; then
                cp -r "$tmp_dir/lib/jdsl" "${INSTALL_DIR}/../lib/"
            else
                cp -r "$tmp_dir/lib" "${INSTALL_DIR}/../lib/"
            fi
        fi
        # Ensure dotenv dependency is installed for binary package
        pip install python-dotenv 2>/dev/null || pip3 install python-dotenv 2>/dev/null || echo -e "${ORANGE}Warning: python-dotenv not installed; binary may fail${NC}"
    elif [ -f "$tmp_dir/jdsl" ]; then
        mv "$tmp_dir/jdsl" "$INSTALL_DIR"
        chmod 755 "${INSTALL_DIR}/jdsl"
        # If source package dirs included alongside binary, install them too
        if [ -d "$tmp_dir/jdsl_pkg" ]; then
            mkdir -p "${INSTALL_DIR}/../lib"
            cp -r "$tmp_dir/jdsl_pkg" "${INSTALL_DIR}/../lib/"
        fi
    elif [ -d "$tmp_dir/bin" ] && [ -d "$tmp_dir/lib" ]; then
        # Already handled above; this catches any extra cases
        mkdir -p "$INSTALL_DIR"
        cp -r "$tmp_dir/bin/jdsl" "$INSTALL_DIR/"
        chmod 755 "${INSTALL_DIR}/jdsl"
        if [ -d "$tmp_dir/lib" ]; then
            mkdir -p "${INSTALL_DIR}/../lib"
            if [ -d "$tmp_dir/lib/jdsl" ]; then
                cp -r "$tmp_dir/lib/jdsl" "${INSTALL_DIR}/../lib/"
            else
                cp -r "$tmp_dir/lib" "${INSTALL_DIR}/../lib/"
            fi
        fi
    elif [ -d "$tmp_dir/jdsl" ]; then
        # Source package: install with pip and create wrapper binary
        pip install "$tmp_dir/jdsl" 2>/dev/null || pip3 install "$tmp_dir/jdsl" 2>/dev/null || { echo -e "${ORANGE}pip install failed; try 'pip install .' from source${NC}"; exit 1; }
        # Create wrapper binary that uses installed package
        echo '#!/usr/bin/env python3
from jdsl.cli import app
if __name__ == "__main__":
    app()' > "${INSTALL_DIR}/jdsl"
        chmod 755 "${INSTALL_DIR}/jdsl"
    else
        echo -e "${RED}Error: Expected binary 'jdsl' or source package in tar${NC}"
        exit 1
    fi
    rm -rf "$tmp_dir"
fi

XDG_CONFIG_HOME=${XDG_CONFIG_HOME:-$HOME/.config}
current_shell=$(basename "$SHELL")
case $current_shell in
    fish)
        config_files="$HOME/.config/fish/config.fish"
    ;;
    zsh)
        config_files="${ZDOTDIR:-$HOME}/.zshrc ${ZDOTDIR:-$HOME}/.zshenv $XDG_CONFIG_HOME/zsh/.zshrc $XDG_CONFIG_HOME/zsh/.zshenv"
    ;;
    bash)
        config_files="$HOME/.bashrc $HOME/.bash_profile $HOME/.profile $XDG_CONFIG_HOME/bash/.bashrc $XDG_CONFIG_HOME/bash/.bash_profile"
    ;;
    ash)
        config_files="$HOME/.ashrc $HOME/.profile /etc/profile"
    ;;
    sh)
        config_files="$HOME/.ashrc $HOME/.profile /etc/profile"
    ;;
    *)
        config_files="$HOME/.bashrc $HOME/.bash_profile $XDG_CONFIG_HOME/bash/.bashrc $XDG_CONFIG_HOME/bash/.bash_profile"
    ;;
esac

if [[ "$no_modify_path" != "true" ]]; then
    config_file=""
    for file in $config_files; do
        if [[ -f $file ]]; then
            config_file=$file
            break
        fi
    done
    if [[ -z $config_file ]]; then
        echo -e "${ORANGE}Warning: No shell config file found; add to PATH manually:${NC}"
        echo -e "  export PATH=$INSTALL_DIR:\$PATH"
    elif [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
        case $current_shell in
            fish)
                echo -e "\n# jdsl" >> "$config_file"
                echo "fish_add_path $INSTALL_DIR" >> "$config_file"
                echo -e "${MUTED}Added $INSTALL_DIR to PATH in $config_file${NC}"
            ;;
            *)
                echo -e "\n# jdsl" >> "$config_file"
                echo "export PATH=$INSTALL_DIR:\$PATH" >> "$config_file"
                echo -e "${MUTED}Added $INSTALL_DIR to PATH in $config_file${NC}"
            ;;
        esac
    fi
fi

# Final banner + info (green)
echo -e "${GREEN}        _        _            _            _     ${NC}"
echo -e "${GREEN}       /\ \     /\ \         / /\         _\ \   ${NC}"
echo -e "${GREEN}       \ \ \   /  \ \____   / /  \       /\__ \  ${NC}"
echo -e "${GREEN}        /\ \_\ / /\ \_____\ / / /\ \__   / /_ \_\ ${NC}"
echo -e "${GREEN}       / /\_// / /\/___  // / /\ \___\ / / /\/__/ ${NC}"
echo -e "${GREEN}  _   / / /  / / /   / / / \ \ \ \/___// / /      ${NC}"
echo -e "${GREEN} /\ \ / / /  / / /   / / /   \ \ \     / / /       ${NC}"
echo -e "${GREEN} \ \_\/ / /  / / /   / / /_    \ \ \   / / / ____   ${NC}"
echo -e "${GREEN}  / / /_/ / /  \ \__/ / //_\__/ / /  / /_/_/ ___/\ ${NC}"
echo -e "${GREEN} / / /__\/ /    \ \___\/ / \ \/___/ /  /_______/\__/ ${NC}"
echo -e "${GREEN}\/_______/      \/_____/   \_____\/   \_______\/  ${NC}"

echo -e "${MUTED}jdsl installed at ${NC}$INSTALL_DIR/jdsl"
echo -e ""
echo -e "${ORANGE}Note: Run 'source ~/.bashrc' (or restart your shell) to use 'jdsl' immediately.${NC}"
echo -e ""
echo -e "${MUTED}Quick start:${NC}"
echo -e "  jdsl run examples/greeter.py"
echo -e ""
echo -e "${MUTED}For API keys:${NC}"
echo -e "  echo 'ANTHROPIC_API_KEY=sk-...' >> .env"
echo -e ""
echo -e "${MUTED}Docs: ${NC}https://cantor-industries.github.io/jdsl-py/"
echo -e ""
