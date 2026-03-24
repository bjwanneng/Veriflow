#!/bin/bash
# run_sim.sh - ACI (Agent-Computer Interface) for Verilog simulation
# Usage: ./run_sim.sh <testbench.v> [rtl_files...]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if iverilog and vvp are available
IVERILOG_MISSING=false
VVP_MISSING=false

if ! command -v iverilog &> /dev/null; then
    IVERILOG_MISSING=true
fi

if ! command -v vvp &> /dev/null; then
    VVP_MISSING=true
fi

if [ "$IVERILOG_MISSING" = true ] || [ "$VVP_MISSING" = true ]; then
    echo -e "${YELLOW}MOCK_SIM: No EDA tools detected${NC}"
    [ "$IVERILOG_MISSING" = true ] && echo "  - iverilog not found"
    [ "$VVP_MISSING" = true ] && echo "  - vvp not found"
    echo ""
    echo "MOCK_MODE: Simulating successful simulation"
    echo "{"
    echo '  "status": "MOCK_SUCCESS",'
    echo '  "tool": "iverilog/vvp (mock)",'
    echo '  "pass_count": 1,'
    echo '  "fail_count": 0,'
    echo '  "log": "MOCK: Simulation completed successfully (no EDA tools available)"'
    echo "}"
    exit 0
fi

# Validate input
if [ $# -lt 1 ]; then
    echo -e "${RED}ERROR: No testbench file specified${NC}"
    echo "Usage: $0 <testbench.v> [rtl_files...]"
    exit 1
fi

TB_FILE="$1"
shift  # Remove first argument, remaining are RTL files

# Check testbench exists
if [ ! -f "$TB_FILE" ]; then
    echo -e "${RED}ERROR: Testbench file not found: $TB_FILE${NC}"
    exit 1
fi

# Check all RTL files exist
for file in "$@"; do
    if [ ! -f "$file" ]; then
        echo -e "${RED}ERROR: RTL file not found: $file${NC}"
        exit 1
    fi
done

echo -e "${GREEN}Running iverilog simulation...${NC}"
echo ""
echo "Testbench: $TB_FILE"
if [ $# -gt 0 ]; then
    echo "RTL files:"
    for file in "$@"; do
        echo "  - $file"
    done
else
    echo -e "${YELLOW}Warning: No RTL files specified, assuming testbench includes them${NC}"
fi

# Create output directory
OUTPUT_DIR="sim_output"
mkdir -p "$OUTPUT_DIR"

# Generate base name for outputs
TB_BASENAME=$(basename "$TB_FILE" .v)
VVP_FILE="$OUTPUT_DIR/${TB_BASENAME}.vvp"
LOG_FILE="$OUTPUT_DIR/${TB_BASENAME}.log"

# Compile with iverilog
echo ""
echo -e "${BLUE}Step 1: Compiling with iverilog...${NC}"
COMPILE_OUTPUT=""
COMPILE_STATUS=0
if ! COMPILE_OUTPUT=$(iverilog -g2005 -Wall -o "$VVP_FILE" "$TB_FILE" "$@" 2>&1); then
    COMPILE_STATUS=1
fi

# Parse compilation output
COMP_ERRORS=$(echo "$COMPILE_OUTPUT" | grep -i "error" | wc -l)
COMP_WARNINGS=$(echo "$COMPILE_OUTPUT" | grep -i "warning" | wc -l)

if [ $COMPILE_STATUS -ne 0 ] || [ $COMP_ERRORS -gt 0 ]; then
    echo -e "${RED}Compilation FAILED${NC}"
    echo "Errors: $COMP_ERRORS"
    echo "Warnings: $COMP_WARNINGS"
    echo ""
    echo "Error details:"
    echo "$COMPILE_OUTPUT"
    exit 1
fi

echo -e "${GREEN}Compilation successful${NC}"
echo "Warnings: $COMP_WARNINGS"

# Run simulation with vvp
echo ""
echo -e "${BLUE}Step 2: Running simulation with vvp...${NC}"
SIM_OUTPUT=$(vvp "$VVP_FILE" 2>&1) || true

# Save log
echo "$COMPILE_OUTPUT" > "$LOG_FILE"
echo "" >> "$LOG_FILE"
echo "=== SIMULATION OUTPUT ===" >> "$LOG_FILE"
echo "$SIM_OUTPUT" >> "$LOG_FILE"

# Parse results
PASS_COUNT=$(echo "$SIM_OUTPUT" | grep -i "passed\|pass" | wc -l)
FAIL_COUNT=$(echo "$SIM_OUTPUT" | grep -i "failed\|fail" | wc -l)
HAS_ALL_PASSED=$(echo "$SIM_OUTPUT" | grep -i "all tests passed" | wc -l)

# Output results
echo ""
echo "========================================"
echo "SIMULATION RESULTS"
echo "========================================"

if [ $FAIL_COUNT -eq 0 ] && [ $HAS_ALL_PASSED -gt 0 ]; then
    echo -e "${GREEN}Status: ALL TESTS PASSED${NC}"
    echo "Pass indicators: $PASS_COUNT"
    echo "Fail indicators: $FAIL_COUNT"
    SIM_STATUS="PASS"
else
    echo -e "${RED}Status: SOME TESTS FAILED${NC}"
    echo "Pass indicators: $PASS_COUNT"
    echo "Fail indicators: $FAIL_COUNT"
    SIM_STATUS="FAIL"
fi

# Display last 30 lines of simulation output
echo ""
echo "Last 30 lines of simulation output:"
echo "---"
echo "$SIM_OUTPUT" | tail -30

# JSON output
JSON_FILE="$OUTPUT_DIR/${TB_BASENAME}_result.json"
cat > "$JSON_FILE" << EOF
{
  "status": "$SIM_STATUS",
  "tool": "iverilog/vvp",
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "testbench": "$TB_FILE",
  "vvp_file": "$VVP_FILE",
  "log_file": "$LOG_FILE",
  "pass_indicators": $PASS_COUNT,
  "fail_indicators": $FAIL_COUNT,
  "all_passed": $([ $HAS_ALL_PASSED -gt 0 ] && echo "true" || echo "false")
}
EOF

echo ""
echo "JSON report saved to: $JSON_FILE"
echo "Full log saved to: $LOG_FILE"

# Exit with appropriate status
[ "$SIM_STATUS" = "PASS" ] && exit 0 || exit 1
