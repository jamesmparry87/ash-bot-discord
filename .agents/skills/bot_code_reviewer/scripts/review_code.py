import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import os
import sys
import argparse
import subprocess

def run_review(dry_run=False):
    repo_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
    os.chdir(repo_dir)

    print("🔍 Starting Bot Code Review...")

    # Check for uncommitted changes
    status_output = subprocess.run(["git", "status", "-s"], capture_output=True, text=True).stdout
    if not status_output:
        print("✅ No uncommitted changes found. Code tree is clean.")
        return

    modified_files = [line.strip().split()[-1] for line in status_output.strip().split("\n")]
    
    if dry_run:
        print(f"🔍 [DRY RUN] Identified {len(modified_files)} modified files:")
        for f in modified_files:
            print(f"   - {f}")
        print("\nRun without --dry-run to perform a full test validation and sprawl check.")
        return
        
    print(f"📄 Found {len(modified_files)} modified files.")
    
    # Check for test files
    test_files = [f for f in modified_files if f.startswith("Live/tests/")]
    logic_files = [f for f in modified_files if f.startswith("Live/bot/")]
    
    # 1. Sprawl check
    if len(logic_files) > 4:
        print("⚠️ WARNING: Code sprawl detected. You have modified more than 4 bot modules.")
        print("   Consider committing current changes or running tests before expanding scope further.")
    
    # 2. Test requirements
    if logic_files and not test_files:
        print("❌ ERROR: You have modified bot logic but no tests have been added or updated in Live/tests/.")
        print("   Rule: Every new feature or modification must have a corresponding test case.")
    elif logic_files:
        print("✅ Test modifications detected alongside logic changes.")

    # 3. Legacy protection
    if any("ash_bot_fallback.py" in f for f in modified_files):
        print("⚠️ WARNING: Modifications to legacy 'ash_bot_fallback.py' detected. Ensure this is intentional.")

    # 4. Run tests
    print("\n🏃 Running pytest to ensure nothing is broken...")
    test_result = subprocess.run(["pytest", "Live/tests/"], capture_output=True, text=True)
    if test_result.returncode != 0:
        print("❌ ERROR: Pytest failed. See output below:")
        print(test_result.stdout[-1000:])
    else:
        print("✅ Pytest passed successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_review(dry_run=args.dry_run)
