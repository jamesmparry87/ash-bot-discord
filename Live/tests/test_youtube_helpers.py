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


@pytest.mark.asyncio
async def test_fetch_vods_channel_logic():
    """Test the VOD channel fetching parses playtime and completion correctly."""
    from bot.integrations.youtube import fetch_vods_channel_recent_videos
    import bot.integrations.youtube as yt_module

    # Mocking out the network calls
    class MockResponse:
        def __init__(self, data):
            self.data = data
            self.status = 200

        async def json(self):
            return self.data

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class MockSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def get(self, url, params=None):
            if 'channels' in url:
                return MockResponse({'items': [{'contentDetails': {'relatedPlaylists': {'uploads': 'PL123'}}}]})
            elif 'playlistItems' in url:
                return MockResponse({
                    'items': [
                        {'contentDetails': {'videoId': 'v1'}, 'snippet': {'title': 'Elden Ring (part 1)'}},
                        {'contentDetails': {'videoId': 'v2'}, 'snippet': {'title': 'First Time Playing Metro 2033 - COMPLETE PLAYTHROUGH'}}
                    ]
                })
            elif 'videos' in url:
                return MockResponse({
                    'items': [
                        {'id': 'v1', 'contentDetails': {'duration': 'PT1H30M15S'}},  # 90 minutes
                        {'id': 'v2', 'contentDetails': {'duration': 'PT10H5M'}}  # 605 minutes
                    ]
                })

    class MockIsoDate:
        @staticmethod
        def parse_duration(d):
            class MockTD:
                def total_seconds(self):
                    return 90 * 60 if '1H30' in d else 605 * 60
            return MockTD()

    with patch('os.getenv', return_value='fake_key'), \
            patch('aiohttp.ClientSession', return_value=MockSession()), \
            patch.dict('sys.modules', {'isodate': MockIsoDate()}):

        results = await fetch_vods_channel_recent_videos("fake_channel_id")

        assert len(results) == 2

        # Check standard video
        v1 = next(r for r in results if r['canonical_name'] == 'Elden Ring')
        assert v1['playtime_minutes'] == 90  # 1H 30M
        assert v1['is_completed'] is False

        # Check complete playthrough video
        v2 = next(r for r in results if r['canonical_name'] == 'Metro 2033')
        assert v2['playtime_minutes'] == 605  # 10H 5M
        assert v2['is_completed'] is True
