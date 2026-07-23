from ..database import get_database

db = get_database()

# This will hold our dynamic and static series names
_known_game_series: set[str] = set()

def initialize_series_list():
    """Fetches series from the DB and merges them with a static list."""
    global _known_game_series
    if not db:
        print("⚠️ Cannot initialize series list: Database not available.")
        return

    # Static list of other popular franchises as a fallback
    static_series_keywords = {
        "final fantasy", "call of duty", "assassin's creed", "the elder scrolls",
        "metal gear", "halo", "gears of war", "mass effect", "dragon age",
        "dark souls", "borderlands", "far cry", "bioshock", "tomb raider",
        "hitman", "battlefield", "mortal kombat", "street fighter", "tekken",
        "sonic", "kingdom hearts", "persona", "fire emblem"
    }

    # Dynamic list from the database
    db_series_names = set(db.get_all_unique_series_names())

    # Combine them
    _known_game_series = db_series_names.union(static_series_keywords)
    print(f"✅ Series list initialized with {len(_known_game_series)} unique series.")

def get_known_game_series() -> set[str]:
    """Returns the set of known game series."""
    return _known_game_series
