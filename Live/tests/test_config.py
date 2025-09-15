"""
Test configuration for Discord bot testing.
This file provides configuration utilities for running tests locally and in CI/CD.
"""
import os
import sys
from typing import Dict, Any, Optional
from pathlib import Path

# Add Live directory to path for imports
LIVE_DIR = Path(__file__).parent / "Live"
sys.path.insert(0, str(LIVE_DIR))

class TestConfig:
    """Test configuration management."""
    
    # Default test environment variables
    DEFAULT_TEST_ENV = {
        'DISCORD_TOKEN': 'test_discord_token_12345',
        'DATABASE_URL': 'postgresql://test:test@localhost/test_discord_bot',
        'GOOGLE_API_KEY': 'test_google_api_key_12345',
        'ANTHROPIC_API_KEY': 'test_anthropic_api_key_12345',
        'YOUTUBE_API_KEY': 'test_youtube_api_key_12345',
        'TWITCH_CLIENT_ID': 'test_twitch_client_id_12345',
        'TWITCH_CLIENT_SECRET': 'test_twitch_client_secret_12345',
        'TEST_MODE': 'true',
        'GUILD_ID': '123456789',
        'VIOLATION_CHANNEL_ID': '123456790',
        'MOD_ALERT_CHANNEL_ID': '123456791',
        'TWITCH_HISTORY_CHANNEL_ID': '123456792',
        'YOUTUBE_HISTORY_CHANNEL_ID': '123456793',
        'RECOMMEND_CHANNEL_ID': '123456794'
    }
    
    @classmethod
    def setup_test_environment(cls, custom_vars: Optional[Dict[str, str]] = None) -> None:
        """Set up test environment variables."""
        env_vars = cls.DEFAULT_TEST_ENV.copy()
        if custom_vars:
            env_vars.update(custom_vars)
        
        for key, value in env_vars.items():
            if key not in os.environ:  # Don't override existing env vars
                os.environ[key] = value
    
    @classmethod
    def get_database_url(cls, use_real_db: bool = False) -> str:
        """Get database URL for testing."""
        if use_real_db:
            # Use real test database (for integration tests)
            return os.getenv('TEST_DATABASE_URL', 'postgresql://test:test@localhost/test_discord_bot')
        else:
            # Use mock database (for unit tests)
            return 'mock://test_database'
    
    @classmethod
    def is_ci_environment(cls) -> bool:
        """Check if running in CI environment."""
        ci_indicators = ['CI', 'GITHUB_ACTIONS', 'GITLAB_CI', 'JENKINS_URL']
        return any(os.getenv(indicator) for indicator in ci_indicators)
    
    @classmethod
    def get_test_discord_token(cls) -> str:
        """Get Discord token for testing."""
        if cls.is_ci_environment():
            # In CI, try to use real test token if available
            return os.getenv('TEST_DISCORD_TOKEN', cls.DEFAULT_TEST_ENV['DISCORD_TOKEN'])
        else:
            # Local development - use mock token
            return cls.DEFAULT_TEST_ENV['DISCORD_TOKEN']
    
    @classmethod
    def get_api_keys(cls) -> Dict[str, str]:
        """Get API keys for testing."""
        return {
            'google': os.getenv('GOOGLE_API_KEY', cls.DEFAULT_TEST_ENV['GOOGLE_API_KEY']),
            'anthropic': os.getenv('ANTHROPIC_API_KEY', cls.DEFAULT_TEST_ENV['ANTHROPIC_API_KEY']),
            'youtube': os.getenv('YOUTUBE_API_KEY', cls.DEFAULT_TEST_ENV['YOUTUBE_API_KEY']),
            'twitch_client_id': os.getenv('TWITCH_CLIENT_ID', cls.DEFAULT_TEST_ENV['TWITCH_CLIENT_ID']),
            'twitch_client_secret': os.getenv('TWITCH_CLIENT_SECRET', cls.DEFAULT_TEST_ENV['TWITCH_CLIENT_SECRET'])
        }
    
    @classmethod
    def validate_environment(cls) -> Dict[str, Any]:
        """Validate test environment setup."""
        validation_results = {
            'valid': True,
            'missing_vars': [],
            'warnings': [],
            'info': []
        }
        
        # Check required environment variables
        required_vars = [
            'DISCORD_TOKEN',
            'DATABASE_URL',
            'GUILD_ID'
        ]
        
        for var in required_vars:
            if not os.getenv(var):
                validation_results['missing_vars'].append(var)
                validation_results['valid'] = False
        
        # Check optional but recommended variables
        optional_vars = [
            'GOOGLE_API_KEY',
            'ANTHROPIC_API_KEY',
            'YOUTUBE_API_KEY',
            'TWITCH_CLIENT_ID',
            'TWITCH_CLIENT_SECRET'
        ]
        
        for var in optional_vars:
            if not os.getenv(var):
                validation_results['warnings'].append(f"{var} not set - some tests may be skipped")
        
        # Environment info
        validation_results['info'].extend([
            f"Running in CI: {cls.is_ci_environment()}",
            f"Database URL: {os.getenv('DATABASE_URL', 'Not set')}",
            f"Test mode: {os.getenv('TEST_MODE', 'Not set')}"
        ])
        
        return validation_results


class MockServices:
    """Mock services for testing."""
    
    @staticmethod
    def mock_discord_responses():
        """Mock Discord API responses."""
        return {
            'user': {
                'id': '123456789',
                'username': 'TestBot',
                'discriminator': '0000'
            },
            'guild': {
                'id': '123456789',
                'name': 'Test Server'
            },
            'channel': {
                'id': '123456790',
                'name': 'test-channel',
                'type': 0
            }
        }
    
    @staticmethod
    def mock_ai_responses():
        """Mock AI service responses."""
        return {
            'gemini': {
                'text': 'Test response from Science Officer Ash. Analysis complete.',
                'safety_ratings': []
            },
            'claude': {
                'content': [{'text': 'Test response from Science Officer Ash. Database query processed.'}],
                'stop_reason': 'end_turn'
            }
        }
    
    @staticmethod
    def mock_youtube_api():
        """Mock YouTube API responses."""
        return {
            'playlists': {
                'items': [
                    {
                        'id': 'PLtest123',
                        'snippet': {
                            'title': 'Test Game Playlist',
                            'description': 'Test game playlist for testing'
                        },
                        'contentDetails': {
                            'itemCount': 10
                        }
                    }
                ]
            },
            'videos': {
                'items': [
                    {
                        'id': 'test123',
                        'snippet': {
                            'title': 'Test Game - Part 1',
                            'publishedAt': '2023-01-01T00:00:00Z'
                        },
                        'contentDetails': {
                            'duration': 'PT30M15S'
                        }
                    }
                ]
            }
        }
    
    @staticmethod
    def mock_twitch_api():
        """Mock Twitch API responses."""
        return {
            'oauth_token': {
                'access_token': 'test_access_token',
                'token_type': 'bearer'
            },
            'user': {
                'data': [
                    {
                        'id': '123456',
                        'login': 'testuser',
                        'display_name': 'TestUser'
                    }
                ]
            },
            'videos': {
                'data': [
                    {
                        'id': '123456',
                        'title': 'Test Game Stream',
                        'created_at': '2023-01-01T00:00:00Z',
                        'url': 'https://twitch.tv/videos/123456',
                        'duration': '1h30m45s'
                    }
                ]
            }
        }


if __name__ == '__main__':
    # Quick environment validation
    TestConfig.setup_test_environment()
    validation = TestConfig.validate_environment()
    
    print("🧪 Test Environment Validation")
    print("=" * 40)
    
    if validation['valid']:
        print("✅ Environment is valid for testing")
    else:
        print("❌ Environment validation failed")
        print("\nMissing required variables:")
        for var in validation['missing_vars']:
            print(f"  - {var}")
    
    if validation['warnings']:
        print("\n⚠️ Warnings:")
        for warning in validation['warnings']:
            print(f"  - {warning}")
    
    if validation['info']:
        print("\n📋 Environment Info:")
        for info in validation['info']:
            print(f"  - {info}")
    
    print("\n🔧 To fix missing variables, run:")
    print("export DISCORD_TOKEN='your_test_token_here'")
    print("export DATABASE_URL='postgresql://user:pass@localhost/test_db'")
