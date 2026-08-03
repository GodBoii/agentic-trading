# python-backend/task_poller.py
"""
Schedule-Aware Task Polling Service
Single background thread that checks for due tasks every 60 seconds.
Uses atomic DB status transition to prevent duplicate execution across workers.
"""

import logging
import time
import threading
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import redis
import config
from supabase_client import supabase_client

logger = logging.getLogger(__name__)


class TaskPoller:
    """
    Background service that polls for scheduled tasks and executes them.
    Only ONE instance across all workers will actually process tasks,
    enforced by atomic DB status transitions (pending -> in_progress).
    """

    def __init__(self, poll_interval: int = 60):
        self.poll_interval = poll_interval
        self.running = False
        self.thread = None
        self.redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)
        self.worker_id = f"{os.getpid()}:{threading.get_ident()}"
        self.lock_key = "locks:task-poller:leader"

    def start(self):
        """Start the background polling thread."""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()
        logger.info(f"Task poller started (interval: {self.poll_interval}s)")

    def stop(self):
        """Stop the background polling thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

    def _poll_loop(self):
        """Main polling loop. Uses Redis lock so only one worker polls."""
        # Random startup delay (1-5s) to stagger workers
        import random
        time.sleep(random.uniform(1, 5))

        while self.running:
            try:
                # Try to acquire leader lock for this cycle (expires in 55s)
                acquired = self.redis_client.set(
                    self.lock_key, self.worker_id, nx=True, ex=55
                )
                if acquired:
                    self._check_and_execute_due_tasks()
            except Exception as e:
                logger.error(f"Error in task poll loop: {e}")

            time.sleep(self.poll_interval)

    def _check_and_execute_due_tasks(self):
        """Query for pending tasks that are due and execute them."""
        try:
            now = datetime.now(timezone.utc)

            # Fetch all pending tasks
            response = supabase_client.table("tasks").select(
                "id, user_id, text, description, priority, deadline, tags, metadata, status"
            ).eq("status", "pending").execute()

            if not response.data:
                return

            for task in response.data:
                if self._is_task_due(task, now):
                    self._dispatch_task(task)

        except Exception as e:
            logger.error(f"Error checking due tasks: {e}")

    def _is_task_due(self, task: Dict[str, Any], now: datetime) -> bool:
        """Check if task's scheduled time has passed."""
        metadata = task.get('metadata', {}) or {}
        next_run_at = metadata.get('next_run_at')

        # Check next_run_at from metadata first
        if next_run_at:
            scheduled = self._parse_datetime(next_run_at)
            if scheduled:
                return now >= scheduled

        # Fallback: check deadline field
        deadline = task.get('deadline')
        if deadline:
            deadline_dt = self._parse_datetime(deadline)
            if deadline_dt:
                return now >= deadline_dt

        # No schedule = immediate execution
        if not next_run_at and not deadline:
            return True

        return False

    def _parse_datetime(self, dt_str: str) -> Optional[datetime]:
        """Parse ISO datetime string to timezone-aware UTC datetime."""
        if not dt_str:
            return None
        try:
            # Handle various formats
            dt_str = dt_str.strip()
            
            # If it has timezone info (e.g., +05:30, +00:00, Z)
            if '+' in dt_str[10:] or dt_str.endswith('Z'):
                dt_str = dt_str.replace('Z', '+00:00')
                dt = datetime.fromisoformat(dt_str)
                # Convert to UTC
                return dt.astimezone(timezone.utc)
            else:
                # No timezone info — assume it's already UTC
                dt = datetime.fromisoformat(dt_str)
                return dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError) as e:
            logger.debug(f"Failed to parse datetime '{dt_str}': {e}")
            return None

    def _dispatch_task(self, task: Dict[str, Any]):
        """Atomically claim and execute a task."""
        task_id = task['id']
        user_id = task['user_id']

        # Atomic claim: only update if still pending (prevents duplicate execution)
        try:
            result = supabase_client.table("tasks").update({
                "status": "in_progress"
            }).eq("id", task_id).eq("status", "pending").execute()

            # If no rows updated, another worker already claimed it
            if not result.data:
                return

        except Exception as e:
            logger.error(f"Failed to claim task {task_id}: {e}")
            return

        logger.info(f"Executing task: {task.get('text')} (id: {task_id})")

        # Execute in a separate thread to not block polling
        execution_thread = threading.Thread(
            target=self._execute_wrapper,
            args=(task_id, user_id, task),
            daemon=True
        )
        execution_thread.start()

    def _execute_wrapper(self, task_id: str, user_id: str, task: Dict[str, Any]):
        """Execute task and handle recurring schedule."""
        try:
            from task_executor import run_autonomous_task
            run_autonomous_task(task_id, user_id, sid=None)

            # Handle recurring schedule after success
            self._handle_recurring(task_id, task)

        except Exception as e:
            logger.error(f"Task execution failed for {task_id}: {e}")
            # Revert to pending
            try:
                supabase_client.table("tasks").update({
                    "status": "pending"
                }).eq("id", task_id).execute()
            except Exception:
                pass

    def _handle_recurring(self, task_id: str, task: Dict[str, Any]):
        """For recurring tasks: compute next run and reset to pending."""
        metadata = task.get('metadata', {}) or {}
        repeat = metadata.get('repeat', 'none')

        if not repeat or repeat == 'none':
            return  # One-time task, stays completed

        next_run = self._compute_next_run(metadata, repeat)
        if not next_run:
            return

        updated_metadata = dict(metadata)
        updated_metadata['next_run_at'] = next_run.isoformat()
        updated_metadata['last_run_at'] = datetime.now(timezone.utc).isoformat()

        try:
            supabase_client.table("tasks").update({
                "status": "pending",
                "metadata": updated_metadata,
                "deadline": next_run.isoformat(),
                "task_work": None,
                "completed_at": None
            }).eq("id", task_id).execute()
            logger.info(f"Recurring task {task_id} rescheduled -> {next_run.isoformat()}")
        except Exception as e:
            logger.error(f"Failed to reschedule task {task_id}: {e}")

    def _compute_next_run(self, metadata: Dict[str, Any], repeat: str) -> Optional[datetime]:
        """Compute the next UTC execution time while preserving the user's local wall-clock time."""
        now_utc = datetime.now(timezone.utc)
        base = self._parse_datetime(metadata.get('next_run_at')) or now_utc
        base = base.astimezone(timezone.utc)

        hour, minute = self._schedule_hour_minute(metadata.get('schedule_time'))
        user_tz = self._user_timezone(metadata)

        if repeat == 'custom':
            custom_interval = metadata.get('custom_interval') or {}
            try:
                value = max(1, int(custom_interval.get('value', 1)))
            except (TypeError, ValueError):
                value = 1
            unit = custom_interval.get('unit', 'days')

            if unit == 'hours':
                candidate = base + timedelta(hours=value)
                while candidate <= now_utc:
                    candidate += timedelta(hours=value)
                return candidate.astimezone(timezone.utc)
            if unit not in {'days', 'weeks'}:
                unit = 'days'

            step = timedelta(days=value if unit == 'days' else value * 7)
            local_candidate = base.astimezone(user_tz) + step
            local_candidate = local_candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)
            while local_candidate.astimezone(timezone.utc) <= now_utc:
                local_candidate += step
            return local_candidate.astimezone(timezone.utc)

        local_candidate = base.astimezone(user_tz)

        if repeat == 'daily':
            local_candidate = self._with_local_time(local_candidate + timedelta(days=1), hour, minute)
            while local_candidate.astimezone(timezone.utc) <= now_utc:
                local_candidate = self._with_local_time(local_candidate + timedelta(days=1), hour, minute)
            return local_candidate.astimezone(timezone.utc)

        if repeat == 'weekdays':
            local_candidate = self._with_local_time(local_candidate + timedelta(days=1), hour, minute)
            while local_candidate.weekday() >= 5 or local_candidate.astimezone(timezone.utc) <= now_utc:
                local_candidate = self._with_local_time(local_candidate + timedelta(days=1), hour, minute)
            return local_candidate.astimezone(timezone.utc)

        if repeat == 'weekly':
            local_candidate = self._with_local_time(local_candidate + timedelta(weeks=1), hour, minute)
            while local_candidate.astimezone(timezone.utc) <= now_utc:
                local_candidate = self._with_local_time(local_candidate + timedelta(weeks=1), hour, minute)
            return local_candidate.astimezone(timezone.utc)

        if repeat == 'monthly':
            anchor_day = self._schedule_day(metadata, local_candidate.day)
            local_candidate = self._add_month(local_candidate, anchor_day, hour, minute)
            while local_candidate.astimezone(timezone.utc) <= now_utc:
                local_candidate = self._add_month(local_candidate, anchor_day, hour, minute)
            return local_candidate.astimezone(timezone.utc)

        return None

    def _schedule_hour_minute(self, schedule_time: Optional[str]) -> tuple[int, int]:
        try:
            hour, minute = map(int, (schedule_time or '09:00').split(':')[:2])
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour, minute
        except (ValueError, TypeError):
            pass
        return 9, 0

    def _user_timezone(self, metadata: Dict[str, Any]):
        tz_name = metadata.get('user_timezone')
        if tz_name:
            try:
                return ZoneInfo(tz_name)
            except ZoneInfoNotFoundError:
                logger.warning("Unknown task timezone '%s'; falling back to stored offset", tz_name)

        try:
            offset_minutes = int(metadata.get('tz_offset_minutes', 0))
        except (TypeError, ValueError):
            offset_minutes = 0
        return timezone(timedelta(minutes=-offset_minutes))

    def _with_local_time(self, dt: datetime, hour: int, minute: int) -> datetime:
        return dt.replace(hour=hour, minute=minute, second=0, microsecond=0)

    def _schedule_day(self, metadata: Dict[str, Any], fallback_day: int) -> int:
        schedule_date = metadata.get('schedule_date')
        if schedule_date:
            try:
                return datetime.fromisoformat(schedule_date).day
            except (TypeError, ValueError):
                pass
        return fallback_day

    def _add_month(self, dt: datetime, anchor_day: int, hour: int, minute: int) -> datetime:
        import calendar

        month = dt.month + 1
        year = dt.year
        if month > 12:
            month = 1
            year += 1
        day = min(anchor_day, calendar.monthrange(year, month)[1])
        return datetime(year, month, day, hour, minute, 0, tzinfo=dt.tzinfo)


# ---------------------------------------------------------------------------
# Global singleton with proper dedup
# ---------------------------------------------------------------------------
_poller_instance = None
_poller_lock = threading.Lock()


def start_task_poller(poll_interval: int = 60):
    """Start the global task poller (only one per process)."""
    global _poller_instance
    with _poller_lock:
        if _poller_instance is not None:
            return  # Already running in this process
        _poller_instance = TaskPoller(poll_interval=poll_interval)
        _poller_instance.start()


def stop_task_poller():
    """Stop the global task poller."""
    global _poller_instance
    with _poller_lock:
        if _poller_instance:
            _poller_instance.stop()
            _poller_instance = None
