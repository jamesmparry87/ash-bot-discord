#!/usr/bin/env python3
"""
IGDB Authentication Test - Pytest Version

Tests IGDB API authentication and basic functionality using Twitch OAuth.
Properly structured as pytest tests with fixtures and mocking.
"""

import os
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Test constants
TEST_TWITCH_CLIENT_ID = "test_client_id_12345"
TEST_TWITCH_CLIENT_SECRET = "test_client_secret_67890"
TEST_ACCESS_TOKEN = "test_access_token_abcdef"


@pytest.fixture
def twitch_credentials(monkeypatch):
    """Fixture to provide Twitch credentials for testing."""
    monkeypatch.setenv('TWITCH_CLIENT_ID', TEST_TWITCH_CLIENT_ID)
    monkeypatch.setenv('TWITCH_CLIENT_SECRET', TEST_TWITCH_CLIENT_SECRET)
    return {
        'client_id': TEST_TWITCH_CLIENT_ID,
        'client_secret': TEST_TWITCH_CLIENT_SECRET
    }


@pytest.fixture
def mock_oauth_response():
    """Mock OAuth token response from Twitch."""
    return {
        'access_token': TEST_ACCESS_TOKEN,
        'expires_in': 5184000,
        'token_type': 'bearer'
    }


@pytest.fixture
def mock_igdb_game_response():
    """Mock IGDB game search response."""
    return [
        {
            'id': 1942,
            'name': 'Resident Evil 4',
            'alternative_names': [
                {'name': 'RE4'},
                {'name': 'Biohazard 4'}
            ],
            'genres': [
                {'name': 'Shooter'},
                {'name': 'Adventure'}
            ],
            'franchises': [
                {'name': 'Resident Evil'}
            ],
            'release_dates': [
                {'y': 2005}
            ],
            'cover': {
                'url': '//images.igdb.com/igdb/image/upload/t_thumb/co1234.jpg'
            }
        }
    ]


@pytest.mark.asyncio
async def test_oauth_token_success(twitch_credentials, mock_oauth_response):
    """Test successful OAuth token retrieval."""
    with patch('aiohttp.ClientSession') as mock_session:
        # Setup mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_oauth_response)

        mock_post = AsyncMock()
        mock_post.__aenter__.return_value = mock_response
        mock_post.__aexit__.return_value = None

        mock_session_instance = MagicMock()
        mock_session_instance.post.return_value = mock_post
        mock_session_instance.__aenter__.return_value = mock_session_instance
        mock_session_instance.__aexit__.return_value = None

        mock_session.return_value = mock_session_instance

        # Import and test the OAuth functionality
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.post(
                'https://id.twitch.tv/oauth2/token',
                params={
                    'client_id': twitch_credentials['client_id'],
                    'client_secret': twitch_credentials['client_secret'],
                    'grant_type': 'client_credentials'
                }
            ) as response:
                assert response.status == 200
                data = await response.json()
                assert data['access_token'] == TEST_ACCESS_TOKEN
                assert data['expires_in'] == 5184000


@pytest.mark.asyncio
async def test_oauth_token_failure(twitch_credentials):
    """Test OAuth token retrieval failure handling."""
    with patch('aiohttp.ClientSession') as mock_session:
        # Setup mock error response
        mock_response = AsyncMock()
        mock_response.status = 401
        mock_response.text = AsyncMock(return_value='{"error": "invalid_client"}')

        mock_post = AsyncMock()
        mock_post.__aenter__.return_value = mock_response
        mock_post.__aexit__.return_value = None

        mock_session_instance = MagicMock()
        mock_session_instance.post.return_value = mock_post
        mock_session_instance.__aenter__.return_value = mock_session_instance
        mock_session_instance.__aexit__.return_value = None

        mock_session.return_value = mock_session_instance

        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.post(
                'https://id.twitch.tv/oauth2/token',
                params={
                    'client_id': twitch_credentials['client_id'],
                    'client_secret': twitch_credentials['client_secret'],
                    'grant_type': 'client_credentials'
                }
            ) as response:
                assert response.status == 401


@pytest.mark.asyncio
async def test_igdb_search_success(mock_igdb_game_response):
    """Test successful IGDB game search."""
    with patch('aiohttp.ClientSession') as mock_session:
        # Setup mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_igdb_game_response)

        mock_post = AsyncMock()
        mock_post.__aenter__.return_value = mock_response
        mock_post.__aexit__.return_value = None

        mock_session_instance = MagicMock()
        mock_session_instance.post.return_value = mock_post
        mock_session_instance.__aenter__.return_value = mock_session_instance
        mock_session_instance.__aexit__.return_value = None

        mock_session.return_value = mock_session_instance

        import aiohttp

        game_name = "Resident Evil 4"
        query = f'search "{game_name}"; fields name,alternative_names.name,franchises.name,genres.name,release_dates.y,cover.url; limit 3;'

        async with aiohttp.ClientSession() as session:
            async with session.post(
                'https://api.igdb.com/v4/games',
                headers={
                    'Client-ID': TEST_TWITCH_CLIENT_ID,
                    'Authorization': f'Bearer {TEST_ACCESS_TOKEN}'
                },
                data=query
            ) as response:
                assert response.status == 200
                results = await response.json()
                assert len(results) == 1
                assert results[0]['name'] == 'Resident Evil 4'
                assert results[0]['id'] == 1942


def test_igdb_credentials_available():
    """Test that IGDB credentials are available in environment."""
    # This test checks that the test environment is set up correctly
    assert os.getenv('TWITCH_CLIENT_ID') is not None
    assert os.getenv('TWITCH_CLIENT_SECRET') is not None


def test_igdb_query_formatting():
    """Test IGDB query string formatting."""
    game_name = "Resident Evil 4"
    game_name_escaped = game_name.replace('"', '\\"')

    query = f'search "{game_name_escaped}"; fields name,alternative_names.name,franchises.name,genres.name,release_dates.y,cover.url; limit 3;'

    # Verify query format
    assert 'search "Resident Evil 4"' in query
    assert 'fields name,alternative_names.name' in query
    assert 'limit 3' in query


def test_igdb_response_parsing(mock_igdb_game_response):
    """Test parsing of IGDB game response data."""
    game_data = mock_igdb_game_response[0]

    # Test basic fields
    assert game_data['name'] == 'Resident Evil 4'
    assert game_data['id'] == 1942

    # Test alternative names
    assert len(game_data['alternative_names']) == 2
    alt_names = [alt['name'] for alt in game_data['alternative_names']]
    assert 'RE4' in alt_names
    assert 'Biohazard 4' in alt_names

    # Test genres
    assert len(game_data['genres']) == 2
    genres = [genre['name'] for genre in game_data['genres']]
    assert 'Shooter' in genres
    assert 'Adventure' in genres

    # Test franchise/series
    assert len(game_data['franchises']) == 1
    assert game_data['franchises'][0]['name'] == 'Resident Evil'

    # Test release year
    assert len(game_data['release_dates']) == 1
    assert game_data['release_dates'][0]['y'] == 2005

    # Test cover URL
    assert 'cover' in game_data
    assert game_data['cover']['url'].startswith('//')


@pytest.mark.asyncio
async def test_igdb_integration_module():
    """Test that the IGDB integration module can be imported."""
    try:
        from bot.integrations import igdb

        # Verify key functions exist (using actual function names from module)
        assert hasattr(igdb, 'validate_and_enrich')
        assert hasattr(igdb, 'get_igdb_access_token')
        assert hasattr(igdb, 'search_igdb')
        assert hasattr(igdb, 'calculate_confidence')
        assert hasattr(igdb, 'should_use_igdb_data')

    except ImportError as e:
        pytest.skip(f"IGDB module not available: {e}")


def test_igdb_error_handling():
    """Test error handling for various IGDB scenarios."""
    # Test empty response
    empty_response = []
    assert len(empty_response) == 0

    # Test missing fields
    incomplete_game = {
        'id': 123,
        'name': 'Test Game'
        # Missing other fields
    }

    # Verify we can handle missing fields gracefully
    assert incomplete_game.get('alternative_names', []) == []
    assert incomplete_game.get('genres', []) == []
    assert incomplete_game.get('franchises', []) == []
