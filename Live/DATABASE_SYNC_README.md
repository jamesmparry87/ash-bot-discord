# Database Sync Utility

This utility syncs data from your live database to staging database for testing purposes.

## Prerequisites

1. **Environment Variables**: Set both `LIVE_DATABASE_URL` and `DATABASE_URL` (staging) in your environment
2. **Dependencies**: Ensure `psycopg2-binary` is installed (included in requirements.txt)
3. **Database Access**: Both databases must be accessible from your current location

## Quick Usage

### Using the Shell Script (Recommended)
```bash
# Navigate to Live directory
cd Live

# Sync all default tables (interactive confirmation)
./sync_staging.sh

# Preview what would be synced (dry run)
./sync_staging.sh --dry-run

# Sync without confirmation prompt
./sync_staging.sh --force

# Sync only specific tables
./sync_staging.sh --tables played_games,trivia_questions

# Get help
./sync_staging.sh --help
```

### Using Python Directly
```bash
# Navigate to Live directory
cd Live

# Basic sync (all default tables)
python database_sync.py

# Dry run to preview changes
python database_sync.py --dry-run

# Force sync without confirmation
python database_sync.py --force

# Sync specific tables only
python database_sync.py --tables played_games,game_recommendations

# Get help
python database_sync.py --help
```

## Default Tables Synced

The utility syncs these tables in dependency order:

1. **played_games** - Main gaming database (needed for statistical analysis)
2. **game_recommendations** - Community game suggestions
3. **trivia_questions** - Trivia system questions
4. **trivia_sessions** - Active/completed trivia sessions
5. **trivia_answers** - User trivia responses

## Safety Features

- **Confirmation Required**: Interactive confirmation before deleting staging data (unless `--force` used)
- **Dry Run Mode**: Preview what would be synced with `--dry-run`
- **Dependency Handling**: Clears tables in reverse order, imports in forward order
- **Batch Processing**: Large tables processed in batches to prevent memory issues
- **Error Recovery**: Transaction rollback on failures
- **Progress Reporting**: Real-time progress for large operations

## Example Output

```
🤖 Database Sync Utility
==================================================
🔗 Connecting to live database...
✓ Connected to live database
🔗 Connecting to staging database...
✓ Connected to staging database
🔍 Validating tables...
📊 Table 'played_games': Live=150 rows, Staging=0 rows
📊 Table 'trivia_questions': Live=25 rows, Staging=0 rows

📋 Sync Summary:
   Source: LIVE_DATABASE_URL
   Target: DATABASE_URL (staging)
   Tables: played_games, trivia_questions
   Mode: LIVE SYNC

⚠️  WARNING: This will PERMANENTLY DELETE all data in staging tables!
Type 'yes' to continue: yes

🚀 Starting sync process...
🗑️  Clearing staging tables...
🗑️  Cleared staging table 'trivia_questions': 0 rows deleted
🗑️  Cleared staging table 'played_games': 0 rows deleted

📥 Importing data from live database...
✅ Synced table 'played_games': 150 rows imported
✅ Synced table 'trivia_questions': 25 rows imported

🎉 SYNC COMPLETED SUCCESSFULLY!
==================================================
📊 played_games:
   Cleared: 0 rows
   Imported: 150 rows
📊 trivia_questions:
   Cleared: 0 rows
   Imported: 25 rows
--------------------------------------------------
📈 Totals:
   Total cleared: 0 rows
   Total imported: 175 rows
```

## Troubleshooting

### Connection Issues
- Verify `LIVE_DATABASE_URL` and `DATABASE_URL` are correct
- Check network connectivity to both databases
- Ensure database credentials are valid

### Permission Issues
```bash
# Make sure the script is executable
chmod +x sync_staging.sh
```

### Missing Tables
- Tables must exist in both live and staging databases
- The bot will create tables automatically on first run
- Check table schemas match between databases

### Large Tables
- The utility handles large tables with batch processing
- Progress is shown for tables > 1000 rows
- Memory usage is optimized for large datasets

## Post-Sync Testing

After syncing, you can test the new functionality:

### Statistical Analysis Queries
```
@Ashbot What game series has Jonesy played for the most minutes?
@Ashbot What game has the highest average playtime per episode?
@Ashbot Which game has the most episodes?
```

### Natural Language Game Queries
```
@Ashbot Has Jonesy played God of War?
@Ashbot What Final Fantasy games has Jonesy played?
@Ashbot What horror games has Jonesy played?
```

### Database Management Commands (Moderators)
```
!gameinfo Dark Souls
!searchplayedgames horror
!listplayedgames Final Fantasy
```

## Security Notes

- Never commit database URLs to version control
- Use environment variables for all database credentials
- Consider using read-only credentials for the live database if possible
- The staging database will be completely overwritten during sync

## Support

If you encounter issues:
1. Check the error messages in the output
2. Verify environment variables are set correctly
3. Ensure both databases are accessible
4. Try a dry run first to identify potential issues
