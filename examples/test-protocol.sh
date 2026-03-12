#!/usr/bin/env bash
# Test Framework Demo - Protocol Validation
#
# This script demonstrates the task monitoring concept without
# requiring internal implementation code.
#
# Usage:
#   bash examples/test-protocol.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=================================="
echo "OpenClaw Protocol Test Demo"
echo "=================================="
echo ""

# Check Python
echo -n "Checking Python... "
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo -e "${GREEN}✓${NC} $PYTHON_VERSION"
else
    echo -e "${RED}✗${NC} Python3 not found"
    exit 1
fi

# Check Python examples exist
echo -n "Checking example files... "
if [[ -f "$SCRIPT_DIR/protocol_messages.py" ]] && [[ -f "$SCRIPT_DIR/task_state_machine.py" ]]; then
    echo -e "${GREEN}✓${NC} Found"
else
    echo -e "${RED}✗${NC} Missing example files"
    exit 1
fi

echo ""
echo "=================================="
echo "Test 1: Protocol Messages"
echo "=================================="
echo ""

python3 "$SCRIPT_DIR/protocol_messages.py"

echo ""
echo "=================================="
echo "Test 2: State Machine"
echo "=================================="
echo ""

python3 "$SCRIPT_DIR/task_state_machine.py"

echo ""
echo "=================================="
echo "All Tests Passed!"
echo "=================================="
echo ""
echo "Next steps:"
echo "  1. Review protocol_messages.py for message format examples"
echo "  2. Review task_state_machine.py for state management"
echo "  3. See examples/README.md for integration guide"
echo "  4. Read AGENT_PROTOCOL.md for full specification"
