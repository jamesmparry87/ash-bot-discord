import pytest
from unittest.mock import MagicMock, patch

from bot.utils.game_series import initialize_series_list, get_known_game_series


def test_initialize_series_list(monkeypatch):
    mock_db = MagicMock()
    mock_db.get_all_unique_series_names.return_value = ["mock_series_1", "mock_series_2"]

    # Need to patch the global db variable in game_series
    monkeypatch.setattr('bot.utils.game_series.db', mock_db)

    initialize_series_list()

    series = get_known_game_series()

    assert "mock_series_1" in series
    assert "mock_series_2" in series
    assert "final fantasy" in series  # From static keywords
    assert "halo" in series


def test_initialize_series_list_no_db(monkeypatch):
    monkeypatch.setattr('bot.utils.game_series.db', None)

    # Should safely return without crashing
    initialize_series_list()

    series = get_known_game_series()
    # It will contain whatever was there before or just static if it was empty,
    # but the key is it doesn't crash when db is None.
    assert isinstance(series, set)
