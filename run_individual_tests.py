"""
Individual Test Runner - Identifies hanging tests
Runs each test in test_functional_core.py separately with timeout
"""

import subprocess
import sys
from pathlib import Path

# Test list in execution order
tests = [
    "Live/tests/test_functional_core.py::TestGamingDatabase::test_game_query_returns_complete_data",
    "Live/tests/test_functional_core.py::TestGamingDatabase::test_statistical_queries_return_valid_data",
    "Live/tests/test_functional_core.py::TestGamingDatabase::test_trivia_session_state_management",
    "Live/tests/test_functional_core.py::TestAIResponses::test_ai_response_filtering_works",
    "Live/tests/test_functional_core.py::TestDataQuality::test_genre_normalization_consistency",
    "Live/tests/test_functional_core.py::TestDataQuality::test_alternative_names_parsing",
    "Live/tests/test_functional_core.py::TestDeploymentReadiness::test_all_required_modules_import",
    "Live/tests/test_functional_core.py::TestDeploymentReadiness::test_database_connection_works",
]

def run_test(test_path, timeout=120):
    """Run a single test with timeout"""
    print(f"\n{'='*70}")
    print(f"Running: {test_path}")
    print(f"Timeout: {timeout}s")
    print('='*70)
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", test_path, "-v", "--tb=short"],
            timeout=timeout,
            capture_output=True,
            text=True
        )
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        if result.returncode == 0:
            print("[PASS]")
            return True
        else:
            print(f"[FAIL] (exit code: {result.returncode})")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"[TIMEOUT] after {timeout}s - TEST HUNG")
        return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False

if __name__ == "__main__":
    print("=" * 70)
    print("INDIVIDUAL TEST RUNNER - Finding hanging tests")
    print("=" * 70)
    
    results = {}
    
    for test in tests:
        test_name = test.split("::")[-1]
        passed = run_test(test, timeout=120)  # 2 minute timeout per test
        results[test_name] = passed
    
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    
    for test_name, passed in results.items():
        status = "[PASS]" if passed else "[FAIL/HANG]"
        print(f"{status}: {test_name}")
    
    # Exit with error if any test failed
    if not all(results.values()):
        sys.exit(1)
