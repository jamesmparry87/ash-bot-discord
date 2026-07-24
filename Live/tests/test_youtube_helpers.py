import pytest
from unittest.mock import MagicMock, patch

from bot.utils.youtube_helpers import attempt_youtube_api_analysis

@pytest.mark.asyncio
async def test_attempt_youtube_api_analysis_no_key(monkeypatch):
    monkeypatch.setattr('os.getenv', lambda key: None if key == 'YOUTUBE_API_KEY' else None)
    result = await attempt_youtube_api_analysis(game_name="Halo")
    assert result is None

@pytest.mark.asyncio
async def test_attempt_youtube_api_analysis_success(monkeypatch):
    monkeypatch.setattr('os.getenv', lambda key: "fake_key" if key == 'YOUTUBE_API_KEY' else None)
    
    # Mock the youtube integration methods
    import bot.integrations.youtube as mock_yt
    mock_get_yt = AsyncMock(return_value={"views": 1000, "full_rankings": []})
    monkeypatch.setattr('bot.integrations.youtube.get_youtube_analytics_for_game', mock_get_yt)
    
    result = await attempt_youtube_api_analysis(game_name="Halo", query_type="general")
    assert result == {"views": 1000, "full_rankings": []}

class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)
