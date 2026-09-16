import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import os
import argparse
import subprocess
import json

def run_pyright(dry_run=False):
    repo_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
    live_dir = os.path.join(repo_dir, "Live")
    
    # Check if pyright is installed
    try:
        version_output = subprocess.run(["pyright", "--version"], capture_output=True, text=True, check=False)
        if "pyright" not in version_output.stdout.lower():
            print("❌ ERROR: pyright is not installed globally or not found in PATH.")
            return
    except Exception:
        print("❌ ERROR: pyright command not found.")
        return

    print("🔍 Pyright is installed and accessible.")
    
    if dry_run:
        print("🔍 [DRY RUN] Pyright validation successful. Run without --dry-run to parse type errors.")
        return

    print("🏃 Running pyright on Live/...")
    os.chdir(live_dir)
    result = subprocess.run(["pyright", "--outputjson"], capture_output=True, text=True)
    
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("❌ ERROR: Failed to parse pyright JSON output.")
        print(result.stdout[:500])
        return
        
    diagnostics = data.get("generalDiagnostics", [])
    if not diagnostics:
        print("✅ Pyright passed! No type errors found.")
        return
        
    print(f"\n⚠️ Found {len(diagnostics)} type errors:")
    for diag in diagnostics:
        file_path = diag.get("file", "")
        msg = diag.get("message", "")
        rule = diag.get("rule", "Unknown Rule")
        line = diag.get("range", {}).get("start", {}).get("line", 0) + 1
        
        print(f"  - {os.path.basename(file_path)}:{line} [{rule}] {msg}")
        
    print("\nNext steps:")
    print(" - For 'reportMissingImports', convert absolute internal imports to relative (e.g. `from .ai_tools import ...`).")
    print(" - For dynamic third-party imports, append `# type: ignore`.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    run_pyright(dry_run=args.dry_run)
