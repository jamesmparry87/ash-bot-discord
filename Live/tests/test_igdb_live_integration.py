"""
Test IGDB integration with live API calls to verify functionality
This ensures IGDB credentials are working and API responses are valid
"""
from bot.integrations import igdb
import pytest
import os
import sys

# Ensure bot modules can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.mark.asyncio
async def test_igdb_authentication():
    """Test that IGDB authentication works with configured credentials"""
    token = await igdb.get_igdb_access_token()

    assert token is not None, "Failed to get IGDB access token - check credentials"
    assert len(token) > 20, "Token seems invalid (too short)"
    print(f"✅ IGDB authentication successful")


@pytest.mark.asyncio
async def test_igdb_known_game_halo():
    """Test IGDB can find and validate 'Halo' with high confidence"""
    result = await igdb.validate_and_enrich("Halo")

    assert result.get('match_found', False), "IGDB should find 'Halo'"
    assert result.get('confidence', 0) >= 0.7, f"Low confidence for 'Halo': {result.get('confidence')}"
    assert 'Halo' in result.get('canonical_name', ''), "Canonical name should contain 'Halo'"

    print(f"✅ Halo → {result.get('canonical_name')} (confidence: {result.get('confidence'):.2f})")


@pytest.mark.asyncio
async def test_igdb_known_game_dark_souls():
    """Test IGDB can find 'Dark Souls 3' with proper number handling"""
    result = await igdb.validate_and_enrich("Dark Souls 3")

    assert result.get('match_found', False), "IGDB should find 'Dark Souls 3'"
    assert result.get('confidence', 0) >= 0.7, f"Low confidence for 'Dark Souls 3': {result.get('confidence')}"
    assert 'Dark Souls' in result.get('canonical_name', ''), "Canonical name should contain 'Dark Souls'"

    print(f"✅ Dark Souls 3 → {result.get('canonical_name')} (confidence: {result.get('confidence'):.2f})")


@pytest.mark.asyncio
async def test_igdb_filters_compound_games():
    """Test that compound/bundle games are properly filtered from search results

    Principle: When IGDB returns compound games (with + or &) in results,
    the code should skip them and select non-compound alternatives.

    Note: We search for a simple game name. If IGDB happens to return
    compound games, they should be filtered out.
    """
    result = await igdb.validate_and_enrich("Halo")

    # The result should NOT be a compound game
    canonical = result.get('canonical_name', '')

    # Verify no compound game indicators in the final result
    assert ' + ' not in canonical, f"Compound games should be filtered, got: '{canonical}'"
    assert ' & ' not in canonical, f"Compound games should be filtered, got: '{canonical}'"

    # Should have found something (Halo is a well-known game)
    assert canonical and 'Halo' in canonical, f"Should find a Halo game, got: '{canonical}'"

    print(f"✅ Compound game filter working: '{canonical}' (no compound indicators)")


@pytest.mark.asyncio
async def test_igdb_returns_alternative_names():
    """Test that IGDB returns alternative names for known games"""
    result = await igdb.validate_and_enrich("Halo")

    if result.get('match_found', False):
        alt_names = result.get('alternative_names', [])
        # Known games usually have alternative names
        assert len(alt_names) > 0, "Known games should have alternative names"

        print(f"✅ Alternative names found: {', '.join(alt_names[:3])}")


@pytest.mark.asyncio
async def test_igdb_handles_accented_characters():
    """Test IGDB can handle games with accented characters"""
    result = await igdb.validate_and_enrich("Pokémon")

    assert result.get('match_found', False), "IGDB should find 'Pokémon'"
    assert 'Pok' in result.get('canonical_name', ''), "Should match Pokémon games"

    print(f"✅ Accented characters: Pokémon → {result.get('canonical_name')}")


@pytest.mark.asyncio
async def test_igdb_returns_metadata():
    """Test that IGDB returns rich metadata for games"""
    result = await igdb.validate_and_enrich("Dark Souls")

    if result.get('match_found', False):
        # Check for metadata fields
        assert 'canonical_name' in result, "Should have canonical_name"
        assert 'confidence' in result, "Should have confidence score"

        # Optional but expected metadata
        has_genre = result.get('genre') is not None
        has_year = result.get('release_year') is not None

        print(f"✅ Metadata: genre={result.get('genre')}, year={result.get('release_year')}")

        # At least some metadata should be present
        assert has_genre or has_year, "Should have at least some metadata"


@pytest.mark.asyncio
async def test_igdb_prefix_matching():
    """Test that prefix matching works for games with subtitles"""
    result = await igdb.validate_and_enrich("Halo")

    # Should match something like "Halo: Combat Evolved" with high confidence
    confidence = result.get('confidence', 0)
    canonical = result.get('canonical_name', '')

    if ':' in canonical and canonical.startswith('Halo'):
        # Prefix match should give high confidence
        assert confidence >= 0.9, f"Prefix match 'Halo' → '{canonical}' should have high confidence, got {confidence}"
        print(f"✅ Prefix matching: 'Halo' → '{canonical}' (confidence: {confidence:.2f})")


# Summary fixture to show test results
@pytest.fixture(scope="session", autouse=True)
def igdb_test_summary():
    """Print summary after all IGDB tests"""
    yield
    print("\n" + "=" * 60)
    print("IGDB LIVE INTEGRATION TESTS COMPLETE")
    print("=" * 60)
