import os
import sys
import argparse
from pathlib import Path
import re

# Determine the absolute path to the Live directory
LIVE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
BOT_DIR = os.path.join(LIVE_DIR, "Live", "bot")

# Regex patterns for deprecated models and parameters
DEPRECATED_MODELS_PATTERN = re.compile(r"['\"]gemini-(1\.5|2\.0|2\.5).*?['\"]")
DEPRECATED_PARAMS_PATTERN = re.compile(r"\b(temperature|top_k|top_p|thinking_budget)\s*=")

def audit_codebase(dry_run: bool):
    print(f"🔍 Scanning {BOT_DIR} for deprecated AI configuration parameters and models...")
    
    issues_found = 0
    files_with_issues = []
    
    for root, dirs, files in os.walk(BOT_DIR):
        for file in files:
            if not file.endswith('.py'):
                continue
                
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, BOT_DIR)
            
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            file_issues = []
            for i, line in enumerate(lines):
                # Check for deprecated parameters
                param_match = DEPRECATED_PARAMS_PATTERN.search(line)
                if param_match:
                    file_issues.append((i + 1, f"Deprecated parameter '{param_match.group(1)}' found: {line.strip()}"))
                
                # Check for legacy models
                model_match = DEPRECATED_MODELS_PATTERN.search(line)
                if model_match:
                    file_issues.append((i + 1, f"Legacy model detected: {line.strip()}"))
                    
            if file_issues:
                files_with_issues.append((rel_path, file_issues))
                issues_found += len(file_issues)
                
    if issues_found == 0:
        print("\n✅ AI Configuration Audit Passed! No deprecated parameters or legacy models found.")
    else:
        print(f"\n❌ AI Configuration Audit Failed! Found {issues_found} potential issues across {len(files_with_issues)} files.")
        
        for rel_path, issues in files_with_issues:
            print(f"\n📄 {rel_path}:")
            for line_num, issue_desc in issues:
                print(f"  Line {line_num}: {issue_desc}")
                
        if dry_run:
            print("\n🔍 [DRY RUN] Would report these to the user for manual remediation.")
        else:
            print("\n⚠️ Please use Antigravity to remove or update these deprecated parameters.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit codebase for deprecated AI configs.")
    parser.add_argument("--dry-run", action="store_true", help="Run in dry-run mode")
    args = parser.parse_args()
    
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')
        
    audit_codebase(args.dry_run)
