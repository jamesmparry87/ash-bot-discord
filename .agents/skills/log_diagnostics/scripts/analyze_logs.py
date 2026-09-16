import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import os
import argparse
import re

def analyze_logs(dry_run=False):
    repo_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
    log_path = os.path.join(repo_dir, "Live", "discord.log")

    print(f"🔍 Analyzing logs at {log_path}...\n")
    
    if not os.path.exists(log_path):
        print(f"❌ ERROR: Log file not found at {log_path}")
        return

    file_size = os.path.getsize(log_path)
    
    if dry_run:
        print(f"🔍 [DRY RUN] Found discord.log ({file_size / 1024:.2f} KB).")
        print("Run without --dry-run to parse stack traces and connection errors.")
        return

    with open(log_path, 'r', encoding='utf-8') as f:
        # Read the last 1000 lines
        lines = f.readlines()
        recent_lines = lines[-1000:]
        
    print(f"📄 Read the last {len(recent_lines)} lines.")
    
    railway_errors = 0
    tracebacks = []
    current_traceback = []
    in_traceback = False
    
    for line in recent_lines:
        if "Connection refused" in line or "server closed the connection unexpectedly" in line:
            railway_errors += 1
            
        if "Traceback (most recent call last):" in line:
            in_traceback = True
            if current_traceback:
                tracebacks.append(current_traceback)
            current_traceback = [line]
        elif in_traceback:
            if line.startswith("20") or line.startswith("[") or not line.strip() or re.match(r'^\w+:', line):
                # End of traceback (or a very short one)
                current_traceback.append(line)
                tracebacks.append(current_traceback)
                in_traceback = False
                current_traceback = []
            else:
                current_traceback.append(line)

    if current_traceback:
        tracebacks.append(current_traceback)

    if railway_errors > 0:
        print(f"\n⚠️ WARNING: Found {railway_errors} instances of Railway Postgres connection drops.")
        print("   This is usually due to idle timeout or concurrency limits on the free tier.")
        
    if tracebacks:
        print(f"\n🔥 Found {len(tracebacks)} recent stack traces. Showing the latest one:")
        print("".join(tracebacks[-1]))
    else:
        print("\n✅ No recent stack traces found in the tail of the log.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    analyze_logs(dry_run=args.dry_run)
