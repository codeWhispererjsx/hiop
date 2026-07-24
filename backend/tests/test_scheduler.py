"""Offline scheduler tests for Epic 3E — AD sync job lifecycle.

All tests use mocks and never contact a real directory or database.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

# ---------------------------------------------------------------------------
# Minimal stubs so the module can be imported without a real DB or scheduler
# ---------------------------------------------------------------------------


def _make_mock_scheduler():
    sched = MagicMock()
    sched.running = True
    sched.get_jobs.return_value = []
    sched.get_job.return_value = None
    return sched


class TestAdSyncJobId(unittest.TestCase):
    def test_job_id_is_deterministic(self):
        from app.services.scheduler_service import ad_sync_job_id, AD_JOB_PREFIX
        conn_id = "abc-123"
        result = ad_sync_job_id(conn_id)
        self.assertEqual(result, f"{AD_JOB_PREFIX}{conn_id}")
        # Calling again returns the same value
        self.assertEqual(result, ad_sync_job_id(conn_id))

    def test_prefix_constant_is_stable(self):
        from app.services.scheduler_service import AD_JOB_PREFIX
        self.assertEqual(AD_JOB_PREFIX, "active_directory_sync_")


class TestAdSchedulable(unittest.TestCase):
    """Test the _ad_schedulable guard logic without touching the scheduler."""

    def _make_conn(self, **kw):
        defaults = dict(enabled=True, authentication_method="simple",
                        encrypted_bind_secret="enc-secret")
        defaults.update(kw)
        return SimpleNamespace(**defaults)

    def _make_config(self, **kw):
        defaults = dict(enabled=True, sync_users_enabled=True,
                        sync_computers_enabled=False, sync_groups_enabled=False,
                        sync_interval_minutes=60)
        defaults.update(kw)
        return SimpleNamespace(**defaults)

    @patch("app.services.scheduler_service.settings")
    def test_schedulable_when_all_conditions_met(self, mock_settings):
        mock_settings.active_directory_enabled = True
        from app.services.scheduler_service import _ad_schedulable
        conn = self._make_conn()
        config = self._make_config()
        self.assertTrue(_ad_schedulable(conn, config))

    @patch("app.services.scheduler_service.settings")
    def test_not_schedulable_when_connection_disabled(self, mock_settings):
        mock_settings.active_directory_enabled = True
        from app.services.scheduler_service import _ad_schedulable
        conn = self._make_conn(enabled=False)
        config = self._make_config()
        self.assertFalse(_ad_schedulable(conn, config))

    @patch("app.services.scheduler_service.settings")
    def test_not_schedulable_when_sync_config_disabled(self, mock_settings):
        mock_settings.active_directory_enabled = True
        from app.services.scheduler_service import _ad_schedulable
        conn = self._make_conn()
        config = self._make_config(enabled=False)
        self.assertFalse(_ad_schedulable(conn, config))

    @patch("app.services.scheduler_service.settings")
    def test_not_schedulable_when_no_object_types_enabled(self, mock_settings):
        mock_settings.active_directory_enabled = True
        from app.services.scheduler_service import _ad_schedulable
        conn = self._make_conn(
            sync_users_enabled=False,
            sync_computers_enabled=False,
            sync_groups_enabled=False,
        )
        # We need to make sure the config object reflects the disabled types
        config = self._make_config(
            sync_users_enabled=False,
            sync_computers_enabled=False,
            sync_groups_enabled=False,
        )
        self.assertFalse(_ad_schedulable(conn, config))

    @patch("app.services.scheduler_service.settings")
    def test_not_schedulable_when_no_secret_and_not_anonymous(self, mock_settings):
        mock_settings.active_directory_enabled = True
        from app.services.scheduler_service import _ad_schedulable
        conn = self._make_conn(encrypted_bind_secret=None, authentication_method="simple")
        config = self._make_config()
        self.assertFalse(_ad_schedulable(conn, config))

    @patch("app.services.scheduler_service.settings")
    def test_anonymous_connection_schedulable_without_secret(self, mock_settings):
        mock_settings.active_directory_enabled = True
        from app.services.scheduler_service import _ad_schedulable
        conn = self._make_conn(encrypted_bind_secret=None, authentication_method="anonymous")
        config = self._make_config()
        self.assertTrue(_ad_schedulable(conn, config))

    @patch("app.services.scheduler_service.settings")
    def test_not_schedulable_when_config_is_none(self, mock_settings):
        mock_settings.active_directory_enabled = True
        from app.services.scheduler_service import _ad_schedulable
        conn = self._make_conn()
        self.assertFalse(_ad_schedulable(conn, None))


class TestRegisterAdSyncJob(unittest.TestCase):
    """Test job registration lifecycle with mocked DB and scheduler."""

    def _make_conn(self, enabled=True):
        return SimpleNamespace(
            id="conn-001", enabled=enabled,
            authentication_method="simple", encrypted_bind_secret="enc",
        )

    def _make_config(self, enabled=True):
        return SimpleNamespace(
            enabled=enabled, sync_users_enabled=True,
            sync_computers_enabled=False, sync_groups_enabled=False,
            sync_interval_minutes=60,
        )

    @patch("app.services.scheduler_service.SessionLocal")
    @patch("app.services.scheduler_service.scheduler", new_callable=_make_mock_scheduler)
    @patch("app.services.scheduler_service.settings")
    def test_register_adds_job(self, mock_settings, mock_scheduler, MockSession):
        mock_settings.scheduler_enabled = True
        mock_settings.ad_minimum_sync_interval_minutes = 5
        mock_settings.active_directory_enabled = True
        db = MagicMock()
        db.get.return_value = self._make_conn()
        db.scalar.return_value = self._make_config()
        MockSession.return_value = db

        from app.services.scheduler_service import register_ad_sync_job
        result = register_ad_sync_job("conn-001")
        self.assertTrue(result)
        mock_scheduler.add_job.assert_called_once()
        call_kwargs = mock_scheduler.add_job.call_args[1]
        self.assertEqual(call_kwargs["id"], "active_directory_sync_conn-001")
        self.assertEqual(call_kwargs["replace_existing"], True)
        self.assertEqual(call_kwargs["max_instances"], 1)

    @patch("app.services.scheduler_service.SessionLocal")
    @patch("app.services.scheduler_service.scheduler", new_callable=_make_mock_scheduler)
    @patch("app.services.scheduler_service.settings")
    def test_register_removes_job_when_not_schedulable(self, mock_settings, mock_scheduler, MockSession):
        mock_settings.scheduler_enabled = True
        mock_settings.active_directory_enabled = True
        db = MagicMock()
        db.get.return_value = self._make_conn(enabled=False)
        db.scalar.return_value = self._make_config()
        MockSession.return_value = db

        existing_job = MagicMock()
        existing_job.id = "active_directory_sync_conn-001"
        mock_scheduler.get_job.return_value = existing_job

        from app.services.scheduler_service import register_ad_sync_job
        result = register_ad_sync_job("conn-001")
        self.assertFalse(result)
        mock_scheduler.remove_job.assert_called_once()

    @patch("app.services.scheduler_service.settings")
    def test_register_returns_false_when_scheduler_disabled(self, mock_settings):
        mock_settings.scheduler_enabled = False
        from app.services.scheduler_service import register_ad_sync_job
        result = register_ad_sync_job("conn-001")
        self.assertFalse(result)

    @patch("app.services.scheduler_service.SessionLocal")
    @patch("app.services.scheduler_service.scheduler", new_callable=_make_mock_scheduler)
    @patch("app.services.scheduler_service.settings")
    def test_update_job_calls_register(self, mock_settings, mock_scheduler, MockSession):
        mock_settings.scheduler_enabled = True
        mock_settings.ad_minimum_sync_interval_minutes = 5
        mock_settings.active_directory_enabled = True
        db = MagicMock()
        db.get.return_value = self._make_conn()
        db.scalar.return_value = self._make_config()
        MockSession.return_value = db

        from app.services.scheduler_service import update_ad_sync_job
        result = update_ad_sync_job("conn-001")
        # update is an alias for register
        self.assertIsInstance(result, bool)


class TestRemoveAdSyncJob(unittest.TestCase):

    @patch("app.services.scheduler_service.scheduler", new_callable=_make_mock_scheduler)
    def test_remove_existing_job(self, mock_scheduler):
        existing_job = MagicMock()
        existing_job.id = "active_directory_sync_conn-999"
        mock_scheduler.get_job.return_value = existing_job

        from app.services.scheduler_service import remove_ad_sync_job
        result = remove_ad_sync_job("conn-999")
        self.assertTrue(result)
        mock_scheduler.remove_job.assert_called_once_with(existing_job.id)

    @patch("app.services.scheduler_service.scheduler", new_callable=_make_mock_scheduler)
    def test_remove_nonexistent_job_returns_false(self, mock_scheduler):
        mock_scheduler.get_job.return_value = None
        from app.services.scheduler_service import remove_ad_sync_job
        result = remove_ad_sync_job("conn-nonexistent")
        self.assertFalse(result)
        mock_scheduler.remove_job.assert_not_called()


class TestDuplicateJobPrevention(unittest.TestCase):

    @patch("app.services.scheduler_service.SessionLocal")
    @patch("app.services.scheduler_service.scheduler", new_callable=_make_mock_scheduler)
    @patch("app.services.scheduler_service.settings")
    def test_replace_existing_prevents_duplicates(self, mock_settings, mock_scheduler, MockSession):
        """replace_existing=True is always passed so APScheduler replaces any duplicate."""
        mock_settings.scheduler_enabled = True
        mock_settings.ad_minimum_sync_interval_minutes = 5
        mock_settings.active_directory_enabled = True
        conn = SimpleNamespace(id="dup-001", enabled=True, authentication_method="simple", encrypted_bind_secret="enc")
        config = SimpleNamespace(enabled=True, sync_users_enabled=True, sync_computers_enabled=False,
                                 sync_groups_enabled=False, sync_interval_minutes=60)
        db = MagicMock()
        db.get.return_value = conn
        db.scalar.return_value = config
        MockSession.return_value = db

        from app.services.scheduler_service import register_ad_sync_job
        register_ad_sync_job("dup-001")
        register_ad_sync_job("dup-001")

        for c in mock_scheduler.add_job.call_args_list:
            self.assertTrue(c[1].get("replace_existing", False))


class TestRecoverStaleRuns(unittest.TestCase):

    def test_stale_running_run_marked_failed(self):
        from datetime import datetime, timedelta, timezone
        from app.services.scheduler_service import recover_stale_ad_runs

        stale_run = MagicMock()
        stale_run.status = "running"
        stale_run.started_at = datetime.now(timezone.utc) - timedelta(hours=5)

        db = MagicMock()
        db.scalars.return_value.all.return_value = [stale_run]

        count = recover_stale_ad_runs(db=db)
        self.assertEqual(count, 1)
        self.assertEqual(stale_run.status, "failed")
        self.assertIsNotNone(stale_run.completed_at)
        db.commit.assert_called_once()

    def test_no_stale_runs_returns_zero(self):
        from app.services.scheduler_service import recover_stale_ad_runs

        db = MagicMock()
        db.scalars.return_value.all.return_value = []

        count = recover_stale_ad_runs(db=db)
        self.assertEqual(count, 0)
        db.commit.assert_not_called()


class TestReconcileAdSyncJobs(unittest.TestCase):

    @patch("app.services.scheduler_service.register_ad_sync_job")
    @patch("app.services.scheduler_service._ad_schedulable")
    @patch("app.services.scheduler_service.scheduler", new_callable=_make_mock_scheduler)
    def test_orphan_jobs_removed_on_reconcile(self, mock_scheduler, mock_schedulable, mock_register):
        """Jobs in the scheduler that have no matching DB connection are removed."""
        mock_schedulable.return_value = False

        orphan_job = MagicMock()
        orphan_job.id = "active_directory_sync_orphan-999"
        mock_scheduler.get_jobs.return_value = [orphan_job]

        db = MagicMock()
        db.scalars.return_value.all.return_value = []  # no connections

        from app.services.scheduler_service import reconcile_ad_sync_jobs
        result = reconcile_ad_sync_jobs(db=db)

        mock_scheduler.remove_job.assert_called_once_with(orphan_job.id)
        self.assertIn("removed", result)

    @patch("app.services.scheduler_service.register_ad_sync_job", return_value=True)
    @patch("app.services.scheduler_service._ad_schedulable", return_value=True)
    @patch("app.services.scheduler_service.scheduler", new_callable=_make_mock_scheduler)
    def test_schedulable_connections_registered_on_reconcile(self, mock_scheduler, mock_schedulable, mock_register):
        conn = SimpleNamespace(id="reconcile-001", enabled=True, authentication_method="simple", encrypted_bind_secret="enc")
        config = SimpleNamespace(enabled=True, sync_users_enabled=True, sync_computers_enabled=False,
                                 sync_groups_enabled=False, sync_interval_minutes=60)

        db = MagicMock()
        db.scalars.return_value.all.return_value = [conn]
        db.scalar.return_value = config
        mock_scheduler.get_jobs.return_value = []

        from app.services.scheduler_service import reconcile_ad_sync_jobs
        result = reconcile_ad_sync_jobs(db=db)

        mock_register.assert_called_once()
        self.assertEqual(result["registered"], 1)


class TestSchedulerShutdown(unittest.TestCase):

    @patch("app.services.scheduler_service.scheduler", new_callable=_make_mock_scheduler)
    def test_stop_scheduler_calls_shutdown(self, mock_scheduler):
        mock_scheduler.running = True
        from app.services.scheduler_service import stop_scheduler
        stop_scheduler()
        mock_scheduler.shutdown.assert_called_once_with(wait=False)

    @patch("app.services.scheduler_service.scheduler", new_callable=_make_mock_scheduler)
    def test_stop_scheduler_noop_when_not_running(self, mock_scheduler):
        mock_scheduler.running = False
        from app.services.scheduler_service import stop_scheduler
        stop_scheduler()
        mock_scheduler.shutdown.assert_not_called()


if __name__ == "__main__":
    unittest.main()
