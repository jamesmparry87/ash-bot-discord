import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import os
import argparse
import sys

TEMPLATE = """import pytest
from unittest.mock import patch
from bot.database.games import get_played_game

# ⚠️ CRITICAL: Never allow tests to connect to the live Railway PostgreSQL database.
# Always use the `db_with_mock_connection` fixture.

@pytest.mark.asyncio
async def test_{feature_name}_success(db_with_mock_connection):
    # Setup mock data
    mock_game_data = {{
        "canonical_name": "Test Game",
        "aliases": ["TestGame1", "TG1"],
        "cover_url": "http://example.com/cover.jpg"
    }}
    
    # Example: Mock the database return value
    with patch('bot.database.games.get_played_game', return_value=mock_game_data):
        
        # Execute your feature logic here
        result = get_played_game("TestGame1")
        
        # Assertions
        assert result is not None
        assert result["canonical_name"] == "Test Game"

@pytest.mark.asyncio
async def test_{feature_name}_not_found(db_with_mock_connection):
    # Setup mock for failure case
    with patch('bot.database.games.get_played_game', return_value=None):
        result = get_played_game("UnknownGame")
        assert result is None
"""

def scaffold_test(feature_name, dry_run=False):
    repo_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
    tests_dir = os.path.join(repo_dir, "Live", "tests")
    
    if not os.path.exists(tests_dir):
        print(f"❌ ERROR: Tests directory not found at {tests_dir}")
        sys.exit(1)
        
    file_name = f"test_{feature_name}.py"
    file_path = os.path.join(tests_dir, file_name)
    
    if os.path.exists(file_path):
        print(f"❌ ERROR: Test file already exists: {file_path}")
        sys.exit(1)
        
    content = TEMPLATE.format(feature_name=feature_name)
    
    if dry_run:
        print(f"🔍 [DRY RUN] Would create test file at: Live/tests/{file_name}")
        print("\n--- File Content Preview ---")
        print(content)
        print("----------------------------\n")
        print("Run without --dry-run to write the file.")
        return
        
    with open(file_path, "w") as f:
        f.write(content)
        
    print(f"✅ Successfully created test scaffold at Live/tests/{file_name}")
    print("Next step: Open the file and adapt the mock logic to match your specific handler.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("feature", help="Name of the feature to test (e.g., ai_handler, twitch_sync)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    scaffold_test(args.feature, args.dry_run)
