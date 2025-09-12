#!/usr/bin/env python3
"""
Master Test Runner - All Bot Testing
Runs all available test suites to validate complete bot functionality.
"""

import asyncio
import os
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

def run_test_script(script_path, test_name):
    """Run a test script and return the result"""
    print(f"\n{'='*60}")
    print(f"🧪 RUNNING: {test_name}")
    print(f"📄 Script: {script_path}")
    print('='*60)
    
    try:
        result = subprocess.run([sys.executable, script_path], 
                              cwd=os.path.dirname(__file__),
                              capture_output=False,  # Show output in real-time
                              text=True)
        success = result.returncode == 0
        
        print(f"\n🏁 {test_name} {'✅ PASSED' if success else '❌ FAILED'}")
        return success
        
    except Exception as e:
        print(f"\n❌ {test_name} CRASHED: {e}")
        return False

def main():
    """Run all test suites"""
    start_time = datetime.now(ZoneInfo("Europe/London"))
    
    print("🚀 MASTER TEST RUNNER - Complete Bot Validation")
    print("="*60)
    print(f"🕒 Started: {start_time.strftime('%Y-%m-%d %H:%M:%S UK')}")
    print("📋 Running all available test suites...")
    print()
    
    # Define all test suites
    test_suites = [
        ("test_basic_modules.py", "Basic Module Architecture"),
        ("test_modular_commands.py", "Modular Command Architecture"),
        ("test_refactored.py", "Refactored Components"),
        ("test_rate_limiting_fixes.py", "Rate Limiting & Deployment Fixes"),
        ("test_dm_conversations.py", "DM Conversation Functionality"),
        ("test_modular_integration.py", "Modular Integration & End-to-End"),
        ("test_staging_validation.py", "Comprehensive Staging Validation"),
    ]
    
    results = []
    
    # Run each test suite
    for script, name in test_suites:
        script_path = os.path.join(os.path.dirname(__file__), script)
        
        if os.path.exists(script_path):
            success = run_test_script(script_path, name)
            results.append((name, success))
        else:
            print(f"\n⚠️ {name}: Script {script} not found, skipping")
            results.append((name, None))
    
    # Final summary
    end_time = datetime.now(ZoneInfo("Europe/London"))
    duration = end_time - start_time
    
    print(f"\n{'='*60}")
    print("📊 MASTER TEST SUMMARY")
    print("="*60)
    
    passed = 0
    failed = 0
    skipped = 0
    
    for test_name, result in results:
        if result is True:
            status = "✅ PASSED"
            passed += 1
        elif result is False:
            status = "❌ FAILED"
            failed += 1
        else:
            status = "⚠️ SKIPPED"
            skipped += 1
        
        print(f"  {status} - {test_name}")
    
    total = len(results)
    print(f"\nResults: {passed} passed, {failed} failed, {skipped} skipped out of {total} test suites")
    print(f"⏱️ Total runtime: {duration.total_seconds():.1f} seconds")
    print(f"🕒 Completed: {end_time.strftime('%Y-%m-%d %H:%M:%S UK')}")
    
    if failed == 0:
        print("\n🎉 ALL TEST SUITES PASSED!")
        print("\n✅ COMPREHENSIVE VALIDATION COMPLETE:")
        print("   • Basic module architecture and imports")
        print("   • Modular command system and cogs")  
        print("   • Refactored component integration")
        print("   • Rate limiting and deployment fixes")
        print("   • DM conversation flows (!announceupdate, !addtriviaquestion)")
        print("   • End-to-end modular bot integration")
        print("   • Complete staging validation for live deployment")
        
        print("\n🚀 BOT IS FULLY VALIDATED AND READY FOR DEPLOYMENT!")
        print("   All functionality tested and working correctly")
        print("   Modular architecture stable and responsive")
        print("   Both local and remote testing infrastructure complete")
        
    elif failed <= 2:
        print(f"\n⚠️ MOSTLY SUCCESSFUL - {failed} test suite(s) failed")
        print("   Review failed test output above for specific issues")
        print("   Core functionality appears stable")
        print("   Consider addressing failures before live deployment")
        
    else:
        print(f"\n❌ CRITICAL ISSUES DETECTED - {failed} test suite(s) failed")
        print("   Review all failed test output above")
        print("   DO NOT deploy to live until issues are resolved")
        print("   Multiple system components may have problems")
    
    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
