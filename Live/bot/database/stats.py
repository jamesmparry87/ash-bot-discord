"""
Database Stats Module - Analytics & AI Usage Tracking

This module handles:
- Platform comparison statistics (YouTube vs Twitch)
- Engagement metrics (views per episode/hour)
- Ranking context for games
- AI usage tracking and quota management
- AI alert logging
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


class StatsDatabase:
    """
    Handles analytics, statistics, and AI usage tracking.

    This class manages platform comparisons, engagement metrics,
    AI quota tracking, and alert logging for the bot.
    """

    def __init__(self, db_manager):
        """
        Initialize stats database handler.

        Args:
            db_manager: DatabaseManager instance for connection access
        """
        self.db = db_manager

    # --- Platform Statistics ---

    def get_platform_comparison_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive platform comparison statistics.

        Compares YouTube vs Twitch content performance including
        game counts, views, and engagement metrics.

        Returns:
            Dict with youtube, twitch, and cross_platform stats
        """
        conn = self.db.get_connection()
        if not conn:
            return {}

        try:
            with conn.cursor() as cur:
                # YouTube statistics
                cur.execute("""
                    SELECT
                        COUNT(*) as game_count,
                        SUM(youtube_views) as total_views,
                        AVG(youtube_views) as avg_views_per_game,
                        SUM(total_episodes) as total_episodes
                    FROM played_games
                    WHERE youtube_playlist_url IS NOT NULL
                    AND youtube_playlist_url != ''
                    AND youtube_views > 0
                """)
                youtube_stats = cur.fetchone()

                # Twitch statistics
                cur.execute("""
                    SELECT
                        COUNT(*) as game_count,
                        SUM(twitch_views) as total_views,
                        AVG(twitch_views) as avg_views_per_game,
                        SUM(total_episodes) as total_vods
                    FROM played_games
                    WHERE twitch_vod_urls IS NOT NULL
                    AND twitch_vod_urls != ''
                    AND twitch_vod_urls != '{}'
                    AND twitch_views > 0
                """)
                twitch_stats = cur.fetchone()

                # Cross-platform games
                cur.execute("""
                    SELECT COUNT(*) as cross_platform_count
                    FROM played_games
                    WHERE youtube_views > 0
                    AND twitch_views > 0
                """)
                cross_platform = cur.fetchone()

                # Safe dictionary access with proper null handling
                youtube_dict = dict(youtube_stats) if youtube_stats else {}
                twitch_dict = dict(twitch_stats) if twitch_stats else {}
                cross_platform_dict = dict(cross_platform) if cross_platform else {}

                return {
                    'youtube': {
                        'game_count': int(youtube_dict.get('game_count') or 0),
                        'total_views': int(youtube_dict.get('total_views') or 0),
                        'avg_views_per_game': round(float(youtube_dict.get('avg_views_per_game') or 0), 1),
                        'total_content': int(youtube_dict.get('total_episodes') or 0)
                    },
                    'twitch': {
                        'game_count': int(twitch_dict.get('game_count') or 0),
                        'total_views': int(twitch_dict.get('total_views') or 0),
                        'avg_views_per_game': round(float(twitch_dict.get('avg_views_per_game') or 0), 1),
                        'total_content': int(twitch_dict.get('total_vods') or 0)
                    },
                    'cross_platform_count': int(cross_platform_dict.get('cross_platform_count') or 0)
                }
        except Exception as e:
            logger.error(f"Error getting platform comparison stats: {e}")
            return {}
        finally:
            if conn:
                conn.close()

    def get_engagement_metrics(self, game_name: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Calculate engagement efficiency metrics (views per episode/hour).

        Args:
            game_name: Optional specific game to get metrics for
            limit: Number of top games to return if game_name is None

        Returns:
            List of game engagement metric dicts
        """
        conn = self.db.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                if game_name:
                    # Get metrics for specific game
                    # ✅ FIX #3: Cast to ::numeric instead of ::float for ROUND() compatibility
                    cur.execute("""
                        SELECT
                            canonical_name,
                            series_name,
                            youtube_views,
                            twitch_views,
                            (COALESCE(youtube_views, 0) + COALESCE(twitch_views, 0)) as total_views,
                            total_episodes,
                            total_playtime_minutes,
                            completion_status,
                            CASE
                                WHEN total_episodes > 0 THEN
                                    ROUND((COALESCE(youtube_views, 0) + COALESCE(twitch_views, 0))::numeric / total_episodes, 1)
                                ELSE 0
                            END as views_per_episode,
                            CASE
                                WHEN total_playtime_minutes > 0 THEN
                                    ROUND((COALESCE(youtube_views, 0) + COALESCE(twitch_views, 0))::numeric / (total_playtime_minutes::numeric / 60), 1)
                                ELSE 0
                            END as views_per_hour
                        FROM played_games
                        WHERE LOWER(canonical_name) LIKE LOWER(%s)
                        AND (youtube_views > 0 OR twitch_views > 0)
                        AND total_episodes > 0
                    """, (f'%{game_name}%',))
                else:
                    # Get top games by engagement rate
                    # ✅ FIX #3: Cast to ::numeric instead of ::float for ROUND() compatibility
                    cur.execute("""
                        SELECT
                            canonical_name,
                            series_name,
                            youtube_views,
                            twitch_views,
                            (COALESCE(youtube_views, 0) + COALESCE(twitch_views, 0)) as total_views,
                            total_episodes,
                            total_playtime_minutes,
                            completion_status,
                            CASE
                                WHEN total_episodes > 0 THEN
                                    ROUND((COALESCE(youtube_views, 0) + COALESCE(twitch_views, 0))::numeric / total_episodes, 1)
                                ELSE 0
                            END as views_per_episode,
                            CASE
                                WHEN total_playtime_minutes > 0 THEN
                                    ROUND((COALESCE(youtube_views, 0) + COALESCE(twitch_views, 0))::numeric / (total_playtime_minutes::numeric / 60), 1)
                                ELSE 0
                            END as views_per_hour
                        FROM played_games
                        WHERE (youtube_views > 0 OR twitch_views > 0)
                        AND total_episodes > 0
                        AND total_playtime_minutes > 0
                        ORDER BY
                            CASE
                                WHEN total_playtime_minutes > 0 THEN
                                    (COALESCE(youtube_views, 0) + COALESCE(twitch_views, 0))::numeric / (total_playtime_minutes::numeric / 60)
                                ELSE 0
                            END DESC
                        LIMIT %s
                    """, (limit,))

                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting engagement metrics: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def get_ranking_context(
        self,
        game_name: str,
        metric: str = "total_views"
    ) -> Dict[str, Any]:
        """
        Get ranking context for a game (where it stands compared to others).

        Args:
            game_name: Game to get ranking for
            metric: Metric to rank by ('total_views', 'youtube_views', 'twitch_views', etc.)

        Returns:
            Dict with rank, total games, and percentile info
        """
        conn = self.db.get_connection()
        if not conn:
            return {}

        try:
            with conn.cursor() as cur:
                # Validate metric to prevent SQL injection
                allowed_metrics = ['total_views', 'youtube_views', 'twitch_views',
                                   'total_playtime_minutes', 'total_episodes']
                if metric not in allowed_metrics:
                    metric = 'total_views'

                # Get the game's value for the metric
                if metric == 'total_views':
                    metric_query = "(COALESCE(youtube_views, 0) + COALESCE(twitch_views, 0))"
                else:
                    metric_query = metric

                query = f"""
                    WITH ranked_games AS (
                        SELECT
                            canonical_name,
                            {metric_query} as metric_value,
                            ROW_NUMBER() OVER (ORDER BY {metric_query} DESC) as rank
                        FROM played_games
                        WHERE {metric_query} > 0
                    )
                    SELECT
                        rank,
                        metric_value,
                        (SELECT COUNT(*) FROM ranked_games) as total_games
                    FROM ranked_games
                    WHERE LOWER(canonical_name) = LOWER(%s)
                """

                cur.execute(query, (game_name,))
                result = cur.fetchone()

                if result:
                    rank_dict = dict(result)
                    rank = int(rank_dict.get('rank', 0))
                    total = int(rank_dict.get('total_games', 0))
                    percentile = round((1 - (rank / total)) * 100, 1) if total > 0 else 0

                    return {
                        'rank': rank,
                        'total_games': total,
                        'percentile': percentile,
                        'metric': metric,
                        'metric_value': rank_dict.get('metric_value')
                    }
                return {}

        except Exception as e:
            logger.error(f"Error getting ranking context for {game_name}: {e}")
            return {}
        finally:
            if conn:
                conn.close()

    # --- AI Usage Tracking ---

    def load_ai_usage_stats(self) -> Optional[Dict[str, Any]]:
        """
        Load AI usage statistics from database for today.

        Creates a new record if one doesn't exist for today.

        Returns:
            Dict with AI usage stats, or None if error
        """
        conn = self.db.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                uk_now = datetime.now(ZoneInfo("Europe/London"))
                today = uk_now.date()

                cur.execute("""
                    SELECT * FROM ai_usage_tracking
                    WHERE tracking_date = %s
                """, (today,))

                result = cur.fetchone()
                if result:
                    stats_dict = dict(result)
                    logger.info(f"Loaded AI usage stats: {stats_dict['daily_requests']} requests today")
                    return stats_dict
                else:
                    # Create initial record for today
                    cur.execute("""
                        INSERT INTO ai_usage_tracking (
                            tracking_date, daily_requests, hourly_requests,
                            daily_errors, last_reset_time, last_hour_reset
                        ) VALUES (%s, 0, 0, 0, %s, %s)
                        RETURNING *
                    """, (today, uk_now, uk_now.hour))

                    conn.commit()
                    new_result = cur.fetchone()
                    if new_result:
                        stats_dict = dict(new_result)
                        logger.info(f"Created new AI usage tracking record for {today}")
                        return stats_dict
                    return None

        except Exception as e:
            logger.error(f"Error loading AI usage stats: {e}")
            return None
        finally:
            if conn:
                conn.close()

    def save_ai_usage_stats(self, stats: Dict[str, Any]) -> bool:
        """
        Save AI usage statistics to database.

        Args:
            stats: Dict containing AI usage statistics

        Returns:
            True if successful, False otherwise
        """
        conn = self.db.get_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                uk_now = datetime.now(ZoneInfo("Europe/London"))
                today = uk_now.date()

                cur.execute("""
                    INSERT INTO ai_usage_tracking (
                        tracking_date, daily_requests, hourly_requests, daily_errors,
                        last_reset_time, last_hour_reset, quota_exhausted,
                        current_model, last_model_switch, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (tracking_date)
                    DO UPDATE SET
                        daily_requests = EXCLUDED.daily_requests,
                        hourly_requests = EXCLUDED.hourly_requests,
                        daily_errors = EXCLUDED.daily_errors,
                        last_reset_time = EXCLUDED.last_reset_time,
                        last_hour_reset = EXCLUDED.last_hour_reset,
                        quota_exhausted = EXCLUDED.quota_exhausted,
                        current_model = EXCLUDED.current_model,
                        last_model_switch = EXCLUDED.last_model_switch,
                        updated_at = EXCLUDED.updated_at
                """, (
                    today,
                    stats.get('daily_requests', 0),
                    stats.get('hourly_requests', 0),
                    stats.get('daily_errors', 0),
                    stats.get('last_reset_time'),
                    stats.get('last_hour_reset', uk_now.hour),
                    stats.get('quota_exhausted', False),
                    stats.get('current_model'),
                    stats.get('last_model_switch'),
                    uk_now
                ))

                conn.commit()
                return True

        except Exception as e:
            logger.error(f"Error saving AI usage stats: {e}")
            conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    def increment_ai_request(self) -> bool:
        """
        Atomically increment AI request counters in database.

        Returns:
            True if successful, False otherwise
        """
        conn = self.db.get_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                uk_now = datetime.now(ZoneInfo("Europe/London"))
                today = uk_now.date()

                cur.execute("""
                    INSERT INTO ai_usage_tracking (
                        tracking_date, daily_requests, hourly_requests,
                        last_reset_time, last_hour_reset, updated_at
                    ) VALUES (%s, 1, 1, %s, %s, %s)
                    ON CONFLICT (tracking_date)
                    DO UPDATE SET
                        daily_requests = ai_usage_tracking.daily_requests + 1,
                        hourly_requests = ai_usage_tracking.hourly_requests + 1,
                        updated_at = %s
                """, (today, uk_now, uk_now.hour, uk_now, uk_now))

                conn.commit()
                return True

        except Exception as e:
            logger.error(f"Error incrementing AI request: {e}")
            conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    def increment_ai_error(self) -> bool:
        """
        Atomically increment AI error counter in database.

        Returns:
            True if successful, False otherwise
        """
        conn = self.db.get_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                uk_now = datetime.now(ZoneInfo("Europe/London"))
                today = uk_now.date()

                cur.execute("""
                    INSERT INTO ai_usage_tracking (
                        tracking_date, daily_errors, updated_at
                    ) VALUES (%s, 1, %s)
                    ON CONFLICT (tracking_date)
                    DO UPDATE SET
                        daily_errors = ai_usage_tracking.daily_errors + 1,
                        updated_at = %s
                """, (today, uk_now, uk_now))

                conn.commit()
                return True

        except Exception as e:
            logger.error(f"Error incrementing AI error: {e}")
            conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    def log_ai_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
        error_details: Optional[Dict[str, Any]] = None,
        dm_sent: bool = False
    ) -> Optional[int]:
        """
        Log an AI alert to the database.

        Args:
            alert_type: Type of alert (e.g., 'quota_exhausted', 'model_switch')
            severity: Alert severity ('low', 'medium', 'high', 'critical')
            message: Alert message
            error_details: Optional structured error data
            dm_sent: Whether moderator was notified via DM

        Returns:
            Alert ID if successful, None otherwise
        """
        conn = self.db.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                uk_now = datetime.now(ZoneInfo("Europe/London"))

                cur.execute("""
                    INSERT INTO ai_alert_log (
                        alert_type, severity, message, error_details,
                        dm_sent, dm_sent_at, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    alert_type,
                    severity,
                    message,
                    json.dumps(error_details) if error_details else None,
                    dm_sent,
                    uk_now if dm_sent else None,
                    uk_now
                ))

                result = cur.fetchone()
                conn.commit()

                if result:
                    alert_id = int(result['id'])  # type: ignore
                    return alert_id
                return None

        except Exception as e:
            logger.error(f"Error logging AI alert: {e}")
            conn.rollback()
            return None
        finally:
            if conn:
                conn.close()

    def get_recent_ai_alerts(
        self,
        alert_type: Optional[str] = None,
        minutes: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get recent AI alerts for aggregation logic.

        Used to prevent alert spam by checking if similar alerts were recently sent.

        Args:
            alert_type: Optional filter by alert type
            minutes: How far back to look (default: 5 minutes)

        Returns:
            List of recent alert dicts
        """
        conn = self.db.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                uk_now = datetime.now(ZoneInfo("Europe/London"))
                cutoff_time = uk_now - timedelta(minutes=minutes)

                if alert_type:
                    cur.execute("""
                        SELECT * FROM ai_alert_log
                        WHERE alert_type = %s
                        AND created_at >= %s
                        ORDER BY created_at DESC
                    """, (alert_type, cutoff_time))
                else:
                    cur.execute("""
                        SELECT * FROM ai_alert_log
                        WHERE created_at >= %s
                        ORDER BY created_at DESC
                    """, (cutoff_time,))

                results = cur.fetchall()
                return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Error getting recent AI alerts: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def get_ai_usage_summary(self, days: int = 7) -> Dict[str, Any]:
        """
        Get AI usage summary for the last N days.

        Args:
            days: Number of days to summarize (default: 7)

        Returns:
            Dict with summary statistics
        """
        conn = self.db.get_connection()
        if not conn:
            return {}

        try:
            with conn.cursor() as cur:
                uk_now = datetime.now(ZoneInfo("Europe/London"))
                cutoff_date = uk_now.date() - timedelta(days=days)

                cur.execute("""
                    SELECT
                        SUM(daily_requests) as total_requests,
                        SUM(daily_errors) as total_errors,
                        AVG(daily_requests) as avg_requests_per_day,
                        MAX(daily_requests) as peak_requests,
                        COUNT(*) as days_with_data
                    FROM ai_usage_tracking
                    WHERE tracking_date >= %s
                """, (cutoff_date,))

                result = cur.fetchone()
                if result:
                    summary = dict(result)
                    return {
                        'total_requests': int(summary.get('total_requests', 0) or 0),
                        'total_errors': int(summary.get('total_errors', 0) or 0),
                        'avg_requests_per_day': round(float(summary.get('avg_requests_per_day', 0) or 0), 1),
                        'peak_requests': int(summary.get('peak_requests', 0) or 0),
                        'days_with_data': int(summary.get('days_with_data', 0) or 0),
                        'timeframe_days': days
                    }
                return {}

        except Exception as e:
            logger.error(f"Error getting AI usage summary: {e}")
            return {}
        finally:
            if conn:
                conn.close()
