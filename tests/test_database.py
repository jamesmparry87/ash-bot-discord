"""
Tests for database operations and functionality.
"""
import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os

# Add the Live directory to sys.path
live_path = os.path.join(os.path.dirname(__file__), '..', 'Live')
if live_path not in sys.path:
    sys.path.insert(0, live_path)

try:
    from database import DatabaseManager  # type: ignore
except ImportError:
    # Create a proper mock DatabaseManager class for type checking
    class DatabaseManager:  # type: ignore
        def __init__(self):
            self.database_url = None
        
        def get_connection(self):
            return None
        
        def get_user_strikes(self, user_id):
            return 0
        
        def set_user_strikes(self, user_id, count):
            pass
        
        def add_user_strike(self, user_id):
            return 1
        
        def get_all_strikes(self):
            return {}
        
        def add_game_recommendation(self, name, reason, added_by):
            return True
        
        def get_all_games(self):
            return []
        
        def game_exists(self, name):
            return False
        
        def get_played_game(self, name):
            return None
        
        def add_played_game(self, **kwargs):
            return True
        
        def update_played_game(self, game_id, **kwargs):
            return True
        
        def _convert_text_to_arrays(self, game_dict):
            return game_dict
        
        def get_config_value(self, key):
            return None
        
        def set_config_value(self, key, value):
            pass
        
        def bulk_import_strikes(self, strike_data):
            return len(strike_data)
        
        def bulk_import_games(self, game_data):
            return len(game_data)
        
        def bulk_import_played_games(self, game_data):
            return len(game_data)
        
        def get_played_games_stats(self):
            return {}
        
        def get_series_by_total_playtime(self):
            return []
        
        def get_games_by_genre_flexible(self, genre):
            return []


class TestDatabaseManager:
    """Test DatabaseManager class functionality."""
    
    def test_database_initialization(self):
        """Test database manager initialization."""
        with patch.dict(os.environ, {'DATABASE_URL': 'test_url'}):
            db = DatabaseManager()
            assert db.database_url == 'test_url'  # type: ignore
    
    def test_database_initialization_no_url(self):
        """Test database manager initialization without DATABASE_URL."""
        with patch.dict(os.environ, {}, clear=True):
            db = DatabaseManager()
            assert db.database_url is None  # type: ignore
    
    @patch('database.psycopg2.connect')
    def test_get_connection_success(self, mock_connect):
        """Test successful database connection."""
        mock_connection = MagicMock()
        mock_connect.return_value = mock_connection
        
        db = DatabaseManager()
        db.database_url = 'test_url'  # type: ignore
        
        connection = db.get_connection()  # type: ignore
        assert connection == mock_connection
        # Connect called during initialization and by get_connection
        assert mock_connect.call_count >= 1
    
    @patch('database.psycopg2.connect')
    def test_get_connection_failure(self, mock_connect):
        """Test database connection failure."""
        mock_connect.side_effect = Exception("Connection failed")
        
        db = DatabaseManager()
        db.database_url = 'test_url'  # type: ignore
        
        connection = db.get_connection()  # type: ignore
        assert connection is None


class TestStrikesOperations:
    """Test strike-related database operations."""
    
    @pytest.fixture
    def db_with_mock_connection(self):
        """Create database manager with mocked connection."""
        db = DatabaseManager()
        db.database_url = 'test_url'  # type: ignore
        
        mock_connection = MagicMock()
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        
        with patch.object(db, 'get_connection', return_value=mock_connection):
            yield db, mock_cursor
    
    def test_get_user_strikes_existing_user(self, db_with_mock_connection):
        """Test getting strikes for existing user."""
        db, mock_cursor = db_with_mock_connection
        mock_cursor.fetchone.return_value = {'strike_count': 3}
        
        result = db.get_user_strikes(123456789)
        assert result == 3
        mock_cursor.execute.assert_called_once()
    
    def test_get_user_strikes_new_user(self, db_with_mock_connection):
        """Test getting strikes for new user (should return 0)."""
        db, mock_cursor = db_with_mock_connection
        mock_cursor.fetchone.return_value = None
        
        result = db.get_user_strikes(123456789)
        assert result == 0
    
    def test_set_user_strikes(self, db_with_mock_connection):
        """Test setting user strikes."""
        db, mock_cursor = db_with_mock_connection
        
        db.set_user_strikes(123456789, 2)
        mock_cursor.execute.assert_called_once()
        # Verify the SQL contains INSERT and ON CONFLICT
        sql_call = mock_cursor.execute.call_args[0][0]
        assert 'INSERT INTO strikes' in sql_call
        assert 'ON CONFLICT' in sql_call
    
    def test_add_user_strike(self, db_with_mock_connection):
        """Test adding a strike to a user."""
        db, mock_cursor = db_with_mock_connection
        
        # Mock get_user_strikes to return current count
        with patch.object(db, 'get_user_strikes', return_value=2):
            with patch.object(db, 'set_user_strikes') as mock_set:
                result = db.add_user_strike(123456789)
                assert result == 3
                mock_set.assert_called_once_with(123456789, 3)
    
    def test_get_all_strikes(self, db_with_mock_connection):
        """Test getting all users with strikes."""
        db, mock_cursor = db_with_mock_connection
        mock_cursor.fetchall.return_value = [{"user_id": 123, "strike_count": 1}, {"user_id": 456, "strike_count": 2}]

        result = db.get_all_strikes()
        expected = {123: 1, 456: 2}
        assert result == expected


class TestGameRecommendations:
    """Test game recommendation database operations."""
    
    @pytest.fixture
    def db_with_mock_connection(self):
        """Create database manager with mocked connection."""
        db = DatabaseManager()
        db.database_url = 'test_url'  # type: ignore
        
        mock_connection = MagicMock()
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        
        with patch.object(db, 'get_connection', return_value=mock_connection):
            yield db, mock_cursor
    
    def test_add_game_recommendation(self, db_with_mock_connection):
        """Test adding a game recommendation."""
        db, mock_cursor = db_with_mock_connection
        
        result = db.add_game_recommendation("Test Game", "Great game", "TestUser")
        assert result is True
        mock_cursor.execute.assert_called_once()
        sql_call = mock_cursor.execute.call_args[0][0]
        assert 'INSERT INTO game_recommendations' in sql_call
    
    def test_get_all_games(self, db_with_mock_connection):
        """Test getting all game recommendations."""
        db, mock_cursor = db_with_mock_connection
        mock_cursor.fetchall.return_value = [
            {'id': 1, 'name': 'Game 1', 'reason': 'Reason 1', 'added_by': 'User1'},
            {'id': 2, 'name': 'Game 2', 'reason': 'Reason 2', 'added_by': 'User2'}
        ]
        
        result = db.get_all_games()
        assert len(result) == 2
        assert result[0]['name'] == 'Game 1'
        assert result[1]['name'] == 'Game 2'
    
    def test_game_exists_exact_match(self, db_with_mock_connection):
        """Test game_exists with exact match."""
        db, mock_cursor = db_with_mock_connection
        
        # Mock get_all_games
        with patch.object(
            db, "get_all_games", return_value=[{"name": "Test Game", "reason": "Great", "added_by": "User"}]
        ):
            result = db.game_exists("Test Game")
            assert result is True
    
    def test_game_exists_fuzzy_match(self, db_with_mock_connection):
        """Test game_exists with fuzzy match."""
        db, mock_cursor = db_with_mock_connection
        
        # Mock get_all_games
        with patch.object(
            db,
            "get_all_games",
            return_value=[{"name": "The Elder Scrolls V: Skyrim", "reason": "Great", "added_by": "User"}],
        ):
            result = db.game_exists("Elder Scrolls Skyrim")
            assert result is True
    
    def test_game_exists_no_match(self, db_with_mock_connection):
        """Test game_exists with no match."""
        db, mock_cursor = db_with_mock_connection
        
        # Mock get_all_games
        with patch.object(
            db, "get_all_games", return_value=[{"name": "Different Game", "reason": "Great", "added_by": "User"}]
        ):
            result = db.game_exists("Test Game")
            assert result is False


class TestPlayedGames:
    """Test played games database operations."""
    
    @pytest.fixture
    def db_with_mock_connection(self):
        """Create database manager with mocked connection."""
        db = DatabaseManager()
        db.database_url = 'test_url'  # type: ignore
        
        mock_connection = MagicMock()
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        
        with patch.object(db, 'get_connection', return_value=mock_connection):
            yield db, mock_cursor
    
    def test_add_played_game_success(self, db_with_mock_connection):
        """Test successfully adding a played game."""
        db, mock_cursor = db_with_mock_connection
        
        result = db.add_played_game(
            canonical_name="Test Game",
            alternative_names=["TG", "Test"],
            series_name="Test Series",
            genre="Action",
            release_year=2023,
            completion_status="completed",
            total_episodes=10
        )
        
        assert result is True
        mock_cursor.execute.assert_called_once()
        sql_call = mock_cursor.execute.call_args[0][0]
        assert 'INSERT INTO played_games' in sql_call
    
    def test_get_played_game_exact_match(self, db_with_mock_connection):
        """Test getting played game with exact canonical name match."""
        db, mock_cursor = db_with_mock_connection
        
        # Mock the exact match query
        mock_cursor.fetchone.side_effect = [
            # First call (exact match) returns result
            {'id': 1, 'canonical_name': 'Test Game', 'alternative_names': 'TG,Test'},
            None,  # Alternative names query (not reached)
            None   # Fuzzy match query (not reached)
        ]

        with patch.object(db, "_convert_text_to_arrays") as mock_convert:
            mock_convert.return_value = {"id": 1, "canonical_name": "Test Game", "alternative_names": ["TG", "Test"]}

            result = db.get_played_game("Test Game")
            assert result is not None
            assert result['canonical_name'] == 'Test Game'
    
    def test_get_played_game_not_found(self, db_with_mock_connection):
        """Test getting played game that doesn't exist."""
        db, mock_cursor = db_with_mock_connection
        
        # Mock all queries to return None
        mock_cursor.fetchone.return_value = None
        mock_cursor.fetchall.return_value = []
        
        result = db.get_played_game("Nonexistent Game")
        assert result is None
    
    def test_update_played_game(self, db_with_mock_connection):
        """Test updating a played game."""
        db, mock_cursor = db_with_mock_connection
        mock_cursor.rowcount = 1  # Simulate successful update
        
        result = db.update_played_game(1, genre="RPG", total_episodes=15)
        assert result is True
        mock_cursor.execute.assert_called_once()
        sql_call = mock_cursor.execute.call_args[0][0]
        assert 'UPDATE played_games SET' in sql_call
    
    def test_convert_text_to_arrays(self):
        """Test conversion of TEXT fields to arrays."""
        db = DatabaseManager()
        
        game_dict = {
            'alternative_names': 'Name1,Name2,Name3',
            'twitch_vod_urls': 'url1,url2,url3',
            'other_field': 'unchanged'
        }
        
        result = db._convert_text_to_arrays(game_dict)  # type: ignore
        
        assert result['alternative_names'] == ['Name1', 'Name2', 'Name3']
        assert result['twitch_vod_urls'] == ['url1', 'url2', 'url3']
        assert result['other_field'] == 'unchanged'
    
    def test_convert_text_to_arrays_empty_fields(self):
        """Test conversion with empty TEXT fields."""
        db = DatabaseManager()

        game_dict = {"alternative_names": "", "twitch_vod_urls": None}

        result = db._convert_text_to_arrays(game_dict)  # type: ignore
        
        assert result['alternative_names'] == []
        assert result['twitch_vod_urls'] == []


class TestConfigOperations:
    """Test configuration-related database operations."""
    
    @pytest.fixture
    def db_with_mock_connection(self):
        """Create database manager with mocked connection."""
        db = DatabaseManager()
        db.database_url = 'test_url'  # type: ignore
        
        mock_connection = MagicMock()
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        
        with patch.object(db, 'get_connection', return_value=mock_connection):
            yield db, mock_cursor
    
    def test_get_config_value_exists(self, db_with_mock_connection):
        """Test getting existing config value."""
        db, mock_cursor = db_with_mock_connection
        mock_cursor.fetchone.return_value = {'value': 'test_value'}
        
        result = db.get_config_value('test_key')
        assert result == 'test_value'
    
    def test_get_config_value_not_exists(self, db_with_mock_connection):
        """Test getting non-existent config value."""
        db, mock_cursor = db_with_mock_connection
        mock_cursor.fetchone.return_value = None
        
        result = db.get_config_value('nonexistent_key')
        assert result is None
    
    def test_set_config_value(self, db_with_mock_connection):
        """Test setting config value."""
        db, mock_cursor = db_with_mock_connection
        
        db.set_config_value('test_key', 'test_value')
        mock_cursor.execute.assert_called_once()
        sql_call = mock_cursor.execute.call_args[0][0]
        assert 'INSERT INTO bot_config' in sql_call
        assert 'ON CONFLICT' in sql_call


class TestBulkOperations:
    """Test bulk import operations."""
    
    @pytest.fixture
    def db_with_mock_connection(self):
        """Create database manager with mocked connection."""
        db = DatabaseManager()
        db.database_url = 'test_url'  # type: ignore
        
        mock_connection = MagicMock()
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        
        with patch.object(db, 'get_connection', return_value=mock_connection):
            yield db, mock_cursor
    
    def test_bulk_import_strikes(self, db_with_mock_connection):
        """Test bulk importing strikes."""
        db, mock_cursor = db_with_mock_connection
        
        strike_data = {123: 1, 456: 2, 789: 3}
        result = db.bulk_import_strikes(strike_data)
        
        assert result == 3
        mock_cursor.executemany.assert_called_once()
    
    def test_bulk_import_games(self, db_with_mock_connection):
        """Test bulk importing game recommendations."""
        db, mock_cursor = db_with_mock_connection
        
        game_data = [
            {'name': 'Game 1', 'reason': 'Reason 1', 'added_by': 'User1'},
            {'name': 'Game 2', 'reason': 'Reason 2', 'added_by': 'User2'}
        ]
        result = db.bulk_import_games(game_data)
        
        assert result == 2
        mock_cursor.executemany.assert_called_once()
    
    def test_bulk_import_played_games(self, db_with_mock_connection):
        """Test bulk importing played games."""
        db, mock_cursor = db_with_mock_connection
        
        # Mock get_played_game to simulate no existing games
        with patch.object(db, 'get_played_game', return_value=None):
            game_data = [
                {
                    'canonical_name': 'Game 1',
                    'alternative_names': ['G1'],
                    'series_name': 'Series 1',
                    'completion_status': 'completed'
                }
            ]
            result = db.bulk_import_played_games(game_data)
            
            assert result == 1
            mock_cursor.execute.assert_called()  # Should be called for insert


class TestStatisticsAndQueries:
    """Test statistical and complex query operations."""
    
    @pytest.fixture
    def db_with_mock_connection(self):
        """Create database manager with mocked connection."""
        db = DatabaseManager()
        db.database_url = 'test_url'  # type: ignore
        
        mock_connection = MagicMock()
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        
        with patch.object(db, 'get_connection', return_value=mock_connection):
            yield db, mock_cursor
    
    def test_get_played_games_stats(self, db_with_mock_connection):
        """Test getting played games statistics."""
        db, mock_cursor = db_with_mock_connection
        
        # Mock multiple cursor results for different queries
        mock_cursor.fetchone.side_effect = [
            {'count': 50},  # Total games
            {'episodes': 500, 'playtime': 30000}  # Episodes and playtime
        ]
        mock_cursor.fetchall.side_effect = [
            [
                {"completion_status": "completed", "count": 30},
                {"completion_status": "ongoing", "count": 20},
            ],  # Status counts
            [{"genre": "Action", "count": 15}, {"genre": "RPG", "count": 10}],  # Top genres
            [{"series_name": "Series A", "count": 5}],  # Top series
        ]
        
        result = db.get_played_games_stats()
        
        assert result['total_games'] == 50
        assert result['total_episodes'] == 500
        assert result['total_playtime_minutes'] == 30000
        assert result['total_playtime_hours'] == 500.0
        assert 'status_counts' in result
        assert 'top_genres' in result
        assert 'top_series' in result
    
    def test_get_series_by_total_playtime(self, db_with_mock_connection):
        """Test getting series ranked by playtime."""
        db, mock_cursor = db_with_mock_connection
        
        mock_cursor.fetchall.return_value = [
            {
                'series_name': 'Series A',
                'game_count': 3,
                'total_playtime_minutes': 1800,
                'total_episodes': 50,
                'avg_playtime_per_game': 600.0
            }
        ]
        
        result = db.get_series_by_total_playtime()
        
        assert len(result) == 1
        assert result[0]['series_name'] == 'Series A'
        assert result[0]['total_playtime_minutes'] == 1800
    
    def test_get_games_by_genre_flexible(self, db_with_mock_connection):
        """Test flexible genre searching."""
        db, mock_cursor = db_with_mock_connection
        
        mock_cursor.fetchall.return_value = [
            {"canonical_name": "Horror Game", "genre": "Survival-Horror", "alternative_names": "HG,Horror"}
        ]
        
        with patch.object(db, '_convert_text_to_arrays') as mock_convert:
            mock_convert.return_value = {
                'canonical_name': 'Horror Game',
                'genre': 'Survival-Horror',
                'alternative_names': ['HG', 'Horror']
            }
            
            result = db.get_games_by_genre_flexible('horror')
            
            assert len(result) == 1
            assert result[0]['canonical_name'] == 'Horror Game'
            mock_cursor.execute.assert_called_once()
            # Verify LIKE query was used
            sql_call = mock_cursor.execute.call_args[0][0]
            assert 'LIKE' in sql_call


if __name__ == '__main__':
    pytest.main([__file__])
