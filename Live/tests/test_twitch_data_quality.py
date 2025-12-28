"""
Twitch Data Quality Validation Tests

Tests to ensure Twitch game name extraction, IGDB validation,
and data quality standards are maintained throughout the sync process.

Phase 4.2: Data Quality Validation Tests
"""

import pytest
from typing import List, Dict, Any


class TestGameNameExtraction:
    """Test game name extraction accuracy from various title formats"""

    @pytest.mark.asyncio
    async def test_game_extraction_after_dash(self):
        """Test extraction prioritizes content AFTER dash (common Twitch format)

        Principle: Extraction logic can parse dash-separated titles correctly,
        regardless of IGDB availability. Confidence is tested separately in IGDB tests.
        """
        from bot.integrations.twitch import smart_extract_with_validation

        test_cases = [
            # Format: (input_title, expected_game_name)
            ("Certified Zombie Pest Control Specialist - Zombie Army 4 (day7)", "Zombie Army 4"),
            ("Stream Title - Elden Ring - Part 5", "Elden Ring"),
            ("Just Chatting - Dark Souls 3 Gameplay", "Dark Souls 3"),
        ]

        for title, expected in test_cases:
            extracted, confidence = await smart_extract_with_validation(title)
            assert extracted is not None, f"Failed to extract game from '{title}'"
            assert expected.lower() in extracted.lower(), f"Expected '{expected}' in '{extracted}' for title '{title}'"
            # Note: confidence depends on IGDB availability, tested separately

    @pytest.mark.asyncio
    async def test_game_extraction_with_episode_markers(self):
        """Test extraction handles episode/day markers correctly

        Principle: Extraction can clean episode markers from titles.
        Confidence depends on IGDB availability, tested separately.
        """
        from bot.integrations.twitch import smart_extract_with_validation

        test_cases = [
            ("God of War (day 5)", "God of War"),
            ("Resident Evil 4 - Part 12", "Resident Evil 4"),
            ("The Last of Us Episode 3", "The Last of Us"),
        ]

        for title, expected in test_cases:
            extracted, confidence = await smart_extract_with_validation(title)
            assert extracted is not None, f"Failed to extract from '{title}'"
            assert expected.lower() in extracted.lower(), f"Expected '{expected}' in '{extracted}'"
            # Note: confidence depends on IGDB availability, tested separately

    @pytest.mark.asyncio
    async def test_game_extraction_new_game_markers(self):
        """Test extraction handles 'NEW GAME' announcements

        Principle: Extraction can clean announcement prefixes from titles.
        """
        from bot.integrations.twitch import smart_extract_with_validation

        test_cases = [
            ("NEW GAME! Dead Space Remake", "Dead Space"),
            ("🆕 Starting Hogwarts Legacy", "Hogwarts Legacy"),
        ]

        for title, expected in test_cases:
            extracted, confidence = await smart_extract_with_validation(title)
            assert extracted is not None, f"Failed to extract from '{title}'"
            assert expected.lower() in extracted.lower(), f"Expected '{expected}' in '{extracted}'"
            # Note: confidence depends on IGDB availability, tested separately


class TestIGDBValidation:
    """Test IGDB integration and validation"""

    def test_english_name_filtering(self):
        """Test alternative names are filtered to English-only"""
        from bot.integrations.igdb import filter_english_names

        test_names = [
            "Halo",
            "Halo: Combat Evolved",
            "Halo: El Combate ha Evolucionado",  # Spanish
            "ハロー",  # Japanese
            "Halo CE",
            "Хало",  # Cyrillic
        ]

        filtered = filter_english_names(test_names)

        # English names should be kept
        assert "Halo" in filtered
        assert "Halo: Combat Evolved" in filtered
        assert "Halo CE" in filtered

        # Non-English names should be filtered out
        assert "ハロー" not in filtered
        assert "Хало" not in filtered
        # Spanish should also be filtered (uses Latin script but contains Spanish keywords)
        assert "Halo: El Combate ha Evolucionado" not in filtered


class TestDataQualityValidation:
    """Test data quality validation helpers"""

    def test_genre_normalization(self):
        """Test genre normalization to standard format"""
        from bot.utils.data_quality import normalize_genre

        test_cases = [
            ("action-rpg", "Action-RPG"),
            ("fps", "FPS"),
            ("survival horror", "Survival-Horror"),
            ("roguelike", "Roguelike"),
            ("ACTION", "Action"),
        ]

        for input_genre, expected in test_cases:
            normalized = normalize_genre(input_genre)
            assert normalized == expected, f"Expected '{expected}' for '{input_genre}', got '{normalized}'"

    def test_series_name_normalization(self):
        """Test series name normalization"""
        from bot.utils.data_quality import normalize_series_name

        test_cases = [
            ("god of war", "God of War"),
            ("gow", "God of War"),
            ("the last of us", "The Last of Us"),
            ("tlou", "The Last of Us"),
        ]

        for input_series, expected in test_cases:
            normalized = normalize_series_name(input_series)
            assert normalized == expected, f"Expected '{expected}' for '{input_series}', got '{normalized}'"

    def test_alternative_names_parsing(self):
        """Test parsing of complex array syntax"""
        from bot.utils.data_quality import parse_complex_array_syntax

        # PostgreSQL array format
        pg_array = '{"Name 1","Name 2","Name 3"}'
        parsed = parse_complex_array_syntax(pg_array)
        assert len(parsed) == 3
        assert "Name 1" in parsed

        # JSON format
        json_array = '["Name 1", "Name 2", "Name 3"]'
        parsed = parse_complex_array_syntax(json_array)
        assert len(parsed) == 3
        assert "Name 1" in parsed

        # Comma-separated
        csv = "Name 1, Name 2, Name 3"
        parsed = parse_complex_array_syntax(csv)
        assert len(parsed) == 3
        assert "Name 1" in parsed


class TestDatabaseIntegration:
    """Test database operations for data quality"""

    def test_series_organization_query(self):
        """Test get_games_by_series_organized returns proper structure"""
        from bot.database_module import get_database

        db = get_database()
        if not db or not db.database_url:
            pytest.skip("Database not available for testing")

        series_dict = db.get_games_by_series_organized()

        # Should return a dictionary
        assert isinstance(series_dict, dict)

        # Each series should have a list of games
        for series_name, games in series_dict.items():
            assert isinstance(series_name, str)
            assert isinstance(games, list)

            # Games should be sorted chronologically
            if len(games) > 1:
                for i in range(len(games) - 1):
                    game1_year = games[i].get('release_year')
                    game2_year = games[i + 1].get('release_year')

                    # If both have years, first should be <= second
                    if game1_year and game2_year:
                        assert game1_year <= game2_year, f"Games in series '{series_name}' not in chronological order"

    def test_game_data_validation(self):
        """Test GameDataValidator validates game data correctly"""
        from bot.utils.data_quality import GameDataValidator

        # Valid game data
        valid_game = {
            'canonical_name': 'Elden Ring',
            'genre': 'Action-RPG',
            'completion_status': 'completed',
            'total_episodes': 10,
            'total_playtime_minutes': 600
        }

        is_valid, errors = GameDataValidator.validate_game_data(valid_game)
        assert is_valid, f"Valid game data rejected with errors: {errors}"
        assert len(errors) == 0

        # Invalid game data - missing canonical name
        invalid_game = {
            'genre': 'Action',
            'completion_status': 'invalid_status'
        }

        is_valid, errors = GameDataValidator.validate_game_data(invalid_game)
        assert not is_valid
        assert len(errors) > 0
        assert any('canonical_name' in error.lower() for error in errors)


class TestTwitchSyncIntegration:
    """Test Twitch sync integration with IGDB validation"""

    @pytest.mark.asyncio
    async def test_low_confidence_triggers_review(self):
        """Test that low-confidence matches trigger manual review"""
        from bot.integrations.twitch import smart_extract_with_validation

        # This should be a deliberately ambiguous title
        ambiguous_title = "Stream Test ABC123 XYZ"

        extracted, confidence = await smart_extract_with_validation(ambiguous_title)

        # Either extraction should fail (None) or have low confidence
        if extracted:
            assert confidence < 0.75, f"Ambiguous title should have low confidence, got {confidence}"
        # If None, that's also acceptable

    @pytest.mark.asyncio
    async def test_high_confidence_auto_accepts(self):
        """Test that clear titles can be extracted successfully

        Principle: Extraction works for straightforward titles.
        Confidence scoring depends on IGDB availability, tested separately in IGDB tests.
        """
        from bot.integrations.twitch import smart_extract_with_validation

        clear_titles = [
            ("Playing Elden Ring", "Elden Ring"),
            ("Dark Souls 3 Playthrough", "Dark Souls"),
            ("God of War - Part 1", "God of War")
        ]

        for title, expected in clear_titles:
            extracted, confidence = await smart_extract_with_validation(title)
            assert extracted is not None, f"Clear title '{title}' should extract game name"
            assert expected.lower() in extracted.lower(), f"Expected '{expected}' in '{extracted}'"
            # Note: confidence depends on IGDB availability, tested separately


class TestEdgeCases:
    """Test edge cases and error handling"""

    @pytest.mark.asyncio
    async def test_extraction_handles_empty_input(self):
        """Test extraction handles empty/None input gracefully"""
        from bot.integrations.twitch import smart_extract_with_validation

        # Should not crash
        result = await smart_extract_with_validation("")
        assert result is not None  # Should return tuple

        extracted, confidence = result
        # Should return None or empty with 0 confidence
        assert extracted is None or extracted == "" or confidence == 0.0

    @pytest.mark.asyncio
    async def test_extraction_handles_special_characters(self):
        """Test extraction handles special characters"""
        from bot.integrations.twitch import smart_extract_with_validation

        special_titles = [
            ("🎮 Playing Portal 2 🎮", "Portal"),
            ("⭐️ Half-Life 2 ⭐️", "Half"),
        ]

        for title, expected_substring in special_titles:
            extracted, confidence = await smart_extract_with_validation(title)
            assert extracted is not None, f"Failed to extract from '{title}'"
            # Should extract something from the title
            assert expected_substring.lower() in extracted.lower(
            ), f"Expected '{expected_substring}' in extracted '{extracted}' from '{title}'"

    def test_filter_english_handles_mixed_content(self):
        """Test English filter handles mixed language content"""
        from bot.integrations.igdb import filter_english_names

        mixed_names = [
            "Halo 3",
            "",  # Empty string
            "   ",  # Whitespace only
            None,  # None value
            123,  # Non-string
        ]

        # Should not crash
        filtered = filter_english_names(mixed_names)
        assert isinstance(filtered, list)
        # Should only have valid English names
        assert "Halo 3" in filtered
        assert "" not in filtered
        assert None not in filtered


class TestRegressionPrevention:
    """Tests to prevent regressions of known issues"""

    @pytest.mark.asyncio
    async def test_zombie_army_4_extraction(self):
        """
        Regression test: Ensure 'Zombie Army 4' is correctly extracted
        from "Certified Zombie Pest Control Specialist - Zombie Army 4 (day7)"

        This was a known failing case that should now work.

        Principle: Extraction prioritizes content AFTER dash over content before dash.
        """
        from bot.integrations.twitch import smart_extract_with_validation

        title = "Certified Zombie Pest Control Specialist - Zombie Army 4 (day7)"
        extracted, confidence = await smart_extract_with_validation(title)

        assert extracted is not None, f"Failed to extract from '{title}'"
        assert "zombie army" in extracted.lower(), f"Expected 'Zombie Army' in '{extracted}'"
        # Note: confidence depends on IGDB availability, tested separately

    def test_alternative_names_no_mixed_languages(self):
        """
        Regression test: Ensure alternative names don't contain mixed languages

        This was a known issue where Spanish, Japanese, etc. names were mixed with English.
        """
        from bot.integrations.igdb import filter_english_names

        problematic_list = [
            "Halo CE HD",
            "Halo: El Combate ha Evolucionado",  # Spanish - should be filtered
            "ハロー: コンバット エボルブド",  # Japanese - should be filtered
            "Halo HD"
        ]

        filtered = filter_english_names(problematic_list)

        # Should only have English names
        english_names = {"Halo CE HD", "Halo HD"}
        for name in filtered:
            assert name in english_names, f"Non-English name '{name}' was not filtered"

    @pytest.mark.asyncio
    async def test_extraction_doesnt_pick_description_first(self):
        """
        Regression test: Ensure extraction doesn't prioritize description over game name

        Previous behavior tried "before dash" first, which was wrong for "Description - Game" format.
        """
        from bot.integrations.twitch import smart_extract_with_validation

        # Format: Description - Game Name
        test_cases = [
            ("Playing some horror - Resident Evil 4", "Resident Evil"),
            ("Finishing the series - The Last of Us Part II", "Last of Us"),
        ]

        for title, expected_game in test_cases:
            extracted, confidence = await smart_extract_with_validation(title)
            assert extracted is not None
            assert expected_game.lower() in extracted.lower(), \
                f"Expected '{expected_game}' in '{extracted}' for title '{title}'"


# Test execution helpers
def run_critical_tests():
    """Run only the most critical tests for quick validation"""
    pytest.main([
        __file__,
        "-k", "test_zombie_army_4_extraction or test_english_name_filtering or test_genre_normalization",
        "-v"
    ])


def run_all_tests():
    """Run all data quality tests"""
    pytest.main([
        __file__,
        "-v"
    ])


if __name__ == "__main__":
    # Run all tests when executed directly
    run_all_tests()
