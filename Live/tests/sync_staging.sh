#!/bin/bash
# Database Sync Utility Wrapper Script
# Makes it easy to sync staging database with live data

set -e  # Exit on any error

echo "🤖 Discord Bot Database Sync"
echo "============================"
echo ""

# Check if we're in the right directory
if [ ! -f "database_sync.py" ]; then
    echo "❌ Error: database_sync.py not found"
    echo "Make sure you're running this from the Live/ directory"
    exit 1
fi

# Check for required environment variables
if [ -z "$LIVE_DATABASE_URL" ]; then
    echo "❌ Error: LIVE_DATABASE_URL environment variable not set"
    exit 1
fi

if [ -z "$DATABASE_URL" ]; then
    echo "❌ Error: DATABASE_URL environment variable not set"
    exit 1
fi

echo "✅ Environment variables found"
echo "   Source: LIVE_DATABASE_URL"
echo "   Target: DATABASE_URL (staging)"
echo ""

# Parse command line arguments
DRY_RUN=""
FORCE=""
TABLES=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN="--dry-run"
            shift
            ;;
        --force)
            FORCE="--force"
            shift
            ;;
        --tables)
            TABLES="--tables $2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dry-run          Show what would be synced without making changes"
            echo "  --force            Skip confirmation prompt"
            echo "  --tables TABLES    Comma-separated list of tables to sync"
            echo "  -h, --help         Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                                    # Sync all default tables"
            echo "  $0 --dry-run                         # Preview sync without changes"
            echo "  $0 --tables played_games             # Sync only played_games table"
            echo "  $0 --force                           # Skip confirmation prompt"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Run the Python script
echo "🚀 Starting database sync..."
python3 database_sync.py $DRY_RUN $FORCE $TABLES

echo ""
echo "✅ Database sync completed!"
