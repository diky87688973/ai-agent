"""异步停止的去重、失败保留、重试和关闭生命周期。"""
import threading
import time
import unittest
from unittest.mock import patch

from agent.shell.session.runner import SessionRunner
from agent.shell.session.stopping import StopOperations, StopWaitTimeout


class StopOperationsTest(unittest.TestCase):
    def test_stop_requested_means_signal_delivered_in_pending_completed_and_failed_states(self):
        stops = StopOperations()
        release = threading.Event()
        try:
            pending = stops.begin("session-A", lambda: None, lambda: release.wait(3), lambda: None)
            self.assertTrue(pending["stop_requested"])
            self.assertEqual(pending["state"], "stopping")
            release.set()
            completed = stops.wait("session-A", pending["stop_id"], 2)
            self.assertTrue(completed["stop_requested"])
            idle = stops.begin("session-B", lambda: None, lambda: False, lambda: None)
            self.assertTrue(stops.wait("session-B", idle["stop_id"], 2)["stop_requested"])
            def failed_signal():
                raise OSError("signal not delivered")
            failed = stops.begin("session-C", failed_signal, lambda: self.fail("must not clean"), lambda: None)
            self.assertEqual(failed["state"], "failed")
            self.assertFalse(failed["stop_requested"])
        finally:
            release.set()
            self.assertTrue(stops.join(2))

    def test_sync_wait_timeout_keeps_original_operation_and_can_query_after_completion(self):
        runner = SessionRunner(app=None, mesh=None)
        release = threading.Event()
        calls = []
        def cleanup():
            calls.append("cleanup")
            release.wait(3)
        try:
            operation = runner.stop_operations.begin("session-A", lambda: None, cleanup, lambda: None)
            with patch.object(runner, "begin_cancel", return_value=operation) as begin:
                started = time.monotonic()
                with self.assertRaises(StopWaitTimeout) as caught:
                    runner.request_cancel("session-A", timeout=0.01)
                self.assertLess(time.monotonic() - started, 1)
                begin.assert_called_once_with("session-A")
            self.assertEqual(caught.exception.stop_id, operation["stop_id"])
            self.assertTrue(runner.stop_operations.blocking("session-A"))
            self.assertEqual(runner.stop_operations.status("session-A", operation["stop_id"])["state"], "stopping")
            release.set()
            self.assertEqual(runner.stop_operations.wait("session-A", operation["stop_id"], 2)["state"], "completed")
            self.assertEqual(calls, ["cleanup"])
        finally:
            release.set()
            self.assertTrue(runner.stop_operations.join(2))

    def test_invalid_wait_budget_is_rejected_before_submitting_stop(self):
        runner = SessionRunner(app=None, mesh=None)
        with patch.object(runner, "begin_cancel") as begin:
            for timeout in (-1, float("nan"), float("inf"), True):
                with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                    runner.request_cancel("session-A", timeout=timeout)
            begin.assert_not_called()

    def test_wait_targets_only_its_operation_and_does_not_join_other_sessions(self):
        stops = StopOperations()
        release = threading.Event()
        try:
            other = stops.begin("session-A", lambda: None, lambda: release.wait(3), lambda: None)
            own = stops.begin("session-B", lambda: None, lambda: None, lambda: None)
            self.assertEqual(stops.wait("session-B", own["stop_id"], 1)["state"], "completed")
            self.assertEqual(stops.status("session-A", other["stop_id"])["state"], "stopping")
            with self.assertRaises(OSError):
                stops.wait("session-B", "unknown-operation", 0)
        finally:
            release.set()
            self.assertTrue(stops.join(2))

    def test_shutdown_reports_turn_and_cleanup_timeouts_independently(self):
        for running_turn, pending_cleanup in ((False, False), (True, False),
                                              (False, True), (True, True)):
            with self.subTest(running_turn=running_turn, pending_cleanup=pending_cleanup):
                release = threading.Event()
                runner = SessionRunner(app=None, mesh=None)
                thread = None
                if running_turn:
                    thread = threading.Thread(target=release.wait, args=(3,), daemon=True)
                    runner._threads["shutdown-turn"] = thread
                    thread.start()
                if pending_cleanup:
                    runner.stop_operations.begin("shutdown-cleanup", lambda: None,
                                                 lambda release=release: release.wait(3), lambda: None)
                try:
                    with patch("agent.shell.session.runner.report_error") as report:
                        self.assertEqual(runner.shutdown(timeout=0.01),
                                         not running_turn and not pending_cleanup)
                    self.assertEqual(report.call_count, int(running_turn) + int(pending_cleanup))
                    turn_reports = [call for call in report.call_args_list
                                    if call.kwargs.get("conversation_id") == "shutdown-turn"]
                    cleanup_reports = [call for call in report.call_args_list
                                       if call.kwargs.get("phase") == "cleanup"]
                    self.assertEqual(len(turn_reports), int(running_turn))
                    self.assertEqual(len(cleanup_reports), int(pending_cleanup))
                finally:
                    release.set()
                    if thread is not None:
                        thread.join(2)
                        self.assertFalse(thread.is_alive())
                    self.assertTrue(runner.stop_operations.join(2))

    def test_returns_before_cleanup_and_deduplicates_pending_requests(self):
        stops = StopOperations()
        entered, release = threading.Event(), threading.Event()
        calls = []

        def cleanup():
            entered.set()
            release.wait(3)
            return True

        try:
            first = stops.begin("session-A", lambda: calls.append("signal"), cleanup,
                                lambda: calls.append("completed"))
            self.assertTrue(entered.wait(1))
            self.assertTrue(stops.blocking("session-A"))
            second = stops.begin("session-A", lambda: self.fail("duplicate signal"), cleanup,
                                 lambda: self.fail("duplicate cleanup"))
            self.assertEqual(first["stop_id"], second["stop_id"])
            self.assertEqual(calls, ["signal"])
            self.assertFalse(stops.join(0.01))
        finally:
            release.set()
            stops.join(2)
        self.assertEqual(stops.status("session-A", first["stop_id"])["state"], "completed")
        self.assertFalse(stops.blocking("session-A"))

    def test_failed_cleanup_remains_blocking_until_explicit_retry(self):
        stops = StopOperations()

        def fail():
            raise OSError("probe failure")

        first = stops.begin("session-A", lambda: None, fail, lambda: self.fail("failure dispatched"))
        self.assertTrue(stops.join(2))
        self.assertTrue(stops.blocking("session-A"))
        self.assertEqual(stops.status("session-A", first["stop_id"])["state"], "failed")
        self.assertTrue(stops.status("session-A", first["stop_id"])["stop_requested"])
        retry = stops.begin("session-A", lambda: None, lambda: True, lambda: None)
        self.assertTrue(stops.join(2))
        self.assertNotEqual(first["stop_id"], retry["stop_id"])
        self.assertIsNone(stops.status("session-A", first["stop_id"]))
        self.assertFalse(stops.blocking("session-A"))

    def test_stop_fences_inflight_start_even_after_cleanup_already_completed(self):
        stops = StopOperations()
        original, other = threading.Event(), threading.Event()
        remove_original = stops.register_start("session-A", original)
        remove_other = stops.register_start("session-B", other)
        try:
            stops.begin("session-A", lambda: None, lambda: True, lambda: None)
            self.assertTrue(stops.join(2))
            self.assertTrue(original.is_set())
            self.assertFalse(other.is_set())
            new_control = threading.Event()
            remove_new = stops.register_start("session-A", new_control)
            self.assertFalse(new_control.is_set())
            remove_new()
        finally:
            remove_original()
            remove_other()

    def test_wait_includes_deferred_dispatch_without_blocking_new_turn(self):
        stops = StopOperations()
        entered, release = threading.Event(), threading.Event()
        def dispatch():
            entered.set()
            release.wait(3)
        try:
            stops.begin("session-A", lambda: None, lambda: True, dispatch)
            self.assertTrue(entered.wait(1))
            self.assertTrue(stops.busy("session-A"))
            self.assertFalse(stops.blocking("session-A"))
            self.assertFalse(stops.join(0.01))
        finally:
            release.set()
            self.assertTrue(stops.join(2))
        self.assertFalse(stops.busy("session-A"))

    def test_thread_start_failure_is_queryable_and_retryable(self):
        stops = StopOperations()
        with patch("agent.shell.session.stopping.thread_with_context", side_effect=RuntimeError("start failed")):
            result = stops.begin("session-A", lambda: None, lambda: self.fail("must not run"), lambda: None)
        self.assertEqual(result["state"], "failed")
        self.assertTrue(stops.blocking("session-A"))
        self.assertIsNone(stops.status("session-B", result["stop_id"]))
