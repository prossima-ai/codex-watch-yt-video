from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIRECTORY = REPOSITORY_ROOT / ".agents" / "skills" / "watch" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

import watch_evidence  # noqa: E402
from watch_evidence import (  # noqa: E402
    CommandResult,
    SubprocessCommandRunner,
    WatchEvidenceRuntime,
)


class LifecycleRunner:
    """A hermetic local-video adapter that records every executable invocation."""

    def __init__(self) -> None:
        self.invocations: list[tuple[str, list[str]]] = []

    def run(
        self,
        executable: str,
        arguments: object,
        *,
        input_fd: int | None = None,
        output_fd: int | None = None,
    ) -> CommandResult:
        del input_fd, output_fd
        args = list(arguments)
        self.invocations.append((executable, args))
        if "--version" in args or "-version" in args:
            return CommandResult(0, "fixture 1.0\n", "")
        if "--verbose" in args:
            return CommandResult(1, "", "[debug] JS runtimes: none\n")
        if "-show_format" in args:
            return CommandResult(
                0,
                json.dumps(
                    {
                        "format": {"duration": "12", "format_name": "mov,mp4"},
                        "streams": [
                            {
                                "codec_type": "video",
                                "codec_name": "h264",
                                "width": 640,
                                "height": 360,
                                "sample_aspect_ratio": "1:1",
                                "display_aspect_ratio": "16:9",
                            }
                        ],
                    }
                ),
                "",
            )
        return CommandResult(0, "", "")


class WorkspaceLifecycleTests(unittest.TestCase):
    def make_runtime(
        self, root: Path
    ) -> tuple[WatchEvidenceRuntime, LifecycleRunner]:
        runner = LifecycleRunner()
        runtime = WatchEvidenceRuntime(
            command_runner=runner,
            find_executable=lambda name: f"/fixture/{name}",
            artifact_root=root / "runtime-root",
        )
        return runtime, runner

    def prepare_local_evidence(
        self, runtime: WatchEvidenceRuntime, source: Path
    ) -> object:
        return runtime.prepare(
            {"sources": [str(source)], "detail": "transcript"}
        )

    def test_default_runtime_root_creates_a_descriptor_bound_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            system_temp = root / "system-temp"
            system_temp.mkdir()
            source = root / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")
            runner = LifecycleRunner()
            runtime = WatchEvidenceRuntime(
                command_runner=runner,
                find_executable=lambda name: f"/fixture/{name}",
            )

            with patch.object(
                watch_evidence.tempfile, "gettempdir", return_value=str(system_temp)
            ):
                outcome = self.prepare_local_evidence(runtime, source)

            self.assertEqual(outcome.state, "partial")
            record = runtime._workspaces[outcome.workspace_id]
            runtime_root = (
                watch_evidence._canonicalize_system_path_alias(system_temp)
                / watch_evidence.RUNTIME_ROOT_DIRECTORY_NAME
            )
            self.assertEqual(record.path.parent, runtime_root)
            self.assertEqual(
                json.loads(
                    (runtime_root / watch_evidence.RUNTIME_ROOT_MARKER_NAME).read_text(
                        encoding="utf-8"
                    )
                ),
                {
                    "schema": watch_evidence.RUNTIME_ROOT_SCHEMA,
                    "version": watch_evidence.RUNTIME_ROOT_VERSION,
                },
            )
            runtime.close()

    def test_fresh_runtime_recovers_a_fixed_root_workspace_for_cleanup_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            system_temp = root / "system-temp"
            system_temp.mkdir()
            source = root / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")
            live_runner = LifecycleRunner()
            live = WatchEvidenceRuntime(
                command_runner=live_runner,
                find_executable=lambda name: f"/fixture/{name}",
            )
            with patch.object(
                watch_evidence.tempfile, "gettempdir", return_value=str(system_temp)
            ):
                initial = self.prepare_local_evidence(live, source)
                live.close()

                recovered_runner = LifecycleRunner()
                recovered = WatchEvidenceRuntime(
                    command_runner=recovered_runner,
                    find_executable=lambda name: f"/fixture/{name}",
                )
                cleaned = recovered.cleanup(initial.workspace_id)

            runtime_root = system_temp / watch_evidence.RUNTIME_ROOT_DIRECTORY_NAME
            workspace = runtime_root / initial.workspace_id
            record = recovered._workspaces[initial.workspace_id]
            self.assertEqual(cleaned.state, "cleanup_incomplete")
            self.assertTrue(workspace.is_dir())
            self.assertTrue(record.cleanup_only)
            self.assertIsNone(record.evidence_handle)
            self.assertFalse(record.reuse_eligible)
            self.assertIsNone(recovered._current_workspace_id)
            self.assertEqual(recovered._evidence_handles, {})
            self.assertEqual(recovered_runner.invocations, [])
            recovered.close()

    def test_fresh_runtime_defers_recovered_cleanup_while_live_lock_is_held(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            system_temp = root / "system-temp"
            system_temp.mkdir()
            source = root / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")
            live_runner = LifecycleRunner()
            live = WatchEvidenceRuntime(
                command_runner=live_runner,
                find_executable=lambda name: f"/fixture/{name}",
            )
            with patch.object(
                watch_evidence.tempfile, "gettempdir", return_value=str(system_temp)
            ):
                initial = self.prepare_local_evidence(live, source)
                recovered_runner = LifecycleRunner()
                recovered = WatchEvidenceRuntime(
                    command_runner=recovered_runner,
                    find_executable=lambda name: f"/fixture/{name}",
                )
                deferred = recovered.cleanup(initial.workspace_id)

            self.assertEqual(deferred.state, "cleanup_deferred")
            self.assertEqual(deferred.disposition.reuse_state, "none")
            self.assertTrue(
                (
                    system_temp
                    / watch_evidence.RUNTIME_ROOT_DIRECTORY_NAME
                    / initial.workspace_id
                ).is_dir()
            )
            self.assertEqual(recovered_runner.invocations, [])
            recovered.close()
            live.close()

    def test_recovery_defers_before_rejecting_a_live_pending_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            system_temp = root / "system-temp"
            system_temp.mkdir()
            source = root / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")
            live = WatchEvidenceRuntime(
                command_runner=LifecycleRunner(),
                find_executable=lambda name: f"/fixture/{name}",
            )
            with patch.object(
                watch_evidence.tempfile, "gettempdir", return_value=str(system_temp)
            ):
                initial = self.prepare_local_evidence(live, source)
                pending = (
                    system_temp
                    / watch_evidence.RUNTIME_ROOT_DIRECTORY_NAME
                    / initial.workspace_id
                    / "pending-output"
                )
                pending.write_bytes(b"still being written")
                recovered = WatchEvidenceRuntime(
                    command_runner=LifecycleRunner(),
                    find_executable=lambda name: f"/fixture/{name}",
                )
                deferred = recovered.cleanup(initial.workspace_id)

            self.assertEqual(deferred.state, "cleanup_deferred")
            self.assertTrue(pending.is_file())
            recovered.close()
            live.close()

    def test_recovery_defers_before_reading_a_partial_live_manifest_then_reopens(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            system_temp = root / "system-temp"
            system_temp.mkdir()
            source = root / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")
            live = WatchEvidenceRuntime(
                command_runner=LifecycleRunner(),
                find_executable=lambda name: f"/fixture/{name}",
            )
            with patch.object(
                watch_evidence.tempfile, "gettempdir", return_value=str(system_temp)
            ):
                initial = self.prepare_local_evidence(live, source)
                manifest = (
                    system_temp
                    / watch_evidence.RUNTIME_ROOT_DIRECTORY_NAME
                    / initial.workspace_id
                    / watch_evidence.WORKSPACE_MANIFEST_NAME
                )
                complete_manifest = manifest.read_bytes()
                manifest.write_bytes(complete_manifest + b'{"record"')
                recovered_runner = LifecycleRunner()
                recovered = WatchEvidenceRuntime(
                    command_runner=recovered_runner,
                    find_executable=lambda name: f"/fixture/{name}",
                )

                deferred = recovered.cleanup(initial.workspace_id)
                self.assertEqual(deferred.state, "cleanup_deferred")
                self.assertNotIn(initial.workspace_id, recovered._workspaces)
                self.assertEqual(recovered_runner.invocations, [])

                manifest.write_bytes(complete_manifest)
                live.close()
                retried = recovered.cleanup(initial.workspace_id)

            self.assertEqual(retried.state, "cleanup_incomplete")
            self.assertTrue(
                initial.workspace_id in recovered._workspaces
                and recovered._workspaces[initial.workspace_id].cleanup_only
            )
            recovered.close()

    def test_fresh_runtime_refuses_invalid_or_tampered_recovery_selectors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            system_temp = root / "system-temp"
            system_temp.mkdir()
            source = root / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")

            invalid_runner = LifecycleRunner()
            invalid_runtime = WatchEvidenceRuntime(
                command_runner=invalid_runner,
                find_executable=lambda name: f"/fixture/{name}",
            )
            with patch.object(
                watch_evidence.tempfile, "gettempdir", return_value=str(system_temp)
            ):
                invalid = invalid_runtime.cleanup(str(source))
                unknown = invalid_runtime.cleanup("workspace_" + "a" * 24)
            self.assertEqual(invalid.state, "cleanup_refused")
            self.assertEqual(unknown.state, "cleanup_refused")
            self.assertFalse(
                (system_temp / watch_evidence.RUNTIME_ROOT_DIRECTORY_NAME).exists()
            )
            self.assertEqual(invalid_runner.invocations, [])
            invalid_runtime.close()

            live_runner = LifecycleRunner()
            live = WatchEvidenceRuntime(
                command_runner=live_runner,
                find_executable=lambda name: f"/fixture/{name}",
            )
            with patch.object(
                watch_evidence.tempfile, "gettempdir", return_value=str(system_temp)
            ):
                initial = self.prepare_local_evidence(live, source)
                live.close()
                marker = (
                    system_temp
                    / watch_evidence.RUNTIME_ROOT_DIRECTORY_NAME
                    / initial.workspace_id
                    / watch_evidence.WORKSPACE_MARKER_NAME
                )
                marker.write_text('{"tampered":true}\n', encoding="utf-8")
                recovered_runner = LifecycleRunner()
                recovered = WatchEvidenceRuntime(
                    command_runner=recovered_runner,
                    find_executable=lambda name: f"/fixture/{name}",
                )
                refused = recovered.cleanup(initial.workspace_id)

            self.assertEqual(refused.state, "cleanup_refused")
            self.assertTrue(marker.is_file())
            self.assertNotIn(initial.workspace_id, recovered._workspaces)
            self.assertEqual(recovered_runner.invocations, [])
            recovered.close()

            injected_runner = LifecycleRunner()
            injected = WatchEvidenceRuntime(
                command_runner=injected_runner,
                find_executable=lambda name: f"/fixture/{name}",
                artifact_root=(
                    system_temp / watch_evidence.RUNTIME_ROOT_DIRECTORY_NAME
                ),
            )
            injected_refusal = injected.cleanup(initial.workspace_id)
            self.assertEqual(injected_refusal.state, "cleanup_refused")
            self.assertEqual(injected_runner.invocations, [])
            injected.close()

    def test_subprocess_runner_streams_to_a_preopened_output_after_name_swap(
        self,
    ) -> None:
        """A child must not select a workspace output name after a name swap."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            moved_workspace = root / "moved-workspace"
            user_directory = root / "user-directory"
            user_directory.mkdir()
            writer = root / "swap-and-write.py"
            writer.write_text(
                "\n".join(
                    (
                        "from pathlib import Path",
                        "import sys",
                        "workspace = Path(sys.argv[1])",
                        "workspace.rename(sys.argv[2])",
                        "workspace.symlink_to(sys.argv[3], target_is_directory=True)",
                        "sys.stdout.buffer.write(b'runtime-owned')",
                    )
                ),
                encoding="utf-8",
            )
            workspace_fd = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY)
            try:
                output_fd = os.open(
                    "caption.vtt",
                    os.O_RDWR
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=workspace_fd,
                )
                try:
                    result = SubprocessCommandRunner().run(
                        sys.executable,
                        [
                            str(writer),
                            str(workspace),
                            str(moved_workspace),
                            str(user_directory),
                        ],
                        output_fd=output_fd,
                    )
                finally:
                    os.close(output_fd)
            finally:
                os.close(workspace_fd)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(workspace.is_symlink())
            self.assertEqual(
                (moved_workspace / "caption.vtt").read_text(encoding="utf-8"),
                "runtime-owned",
            )
            self.assertFalse((user_directory / "caption.vtt").exists())

    def test_opaque_same_task_handle_reuses_immutable_evidence_without_commands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")
            runtime, runner = self.make_runtime(root)

            initial = self.prepare_local_evidence(runtime, source)
            invocations_before_reuse = list(runner.invocations)
            reused = runtime.prepare(
                {"sources": [str(source)], "question": "What evidence is retained?"},
                prior_evidence=initial,
            )

        self.assertEqual(initial.workspace_id, reused.workspace_id)
        self.assertEqual(initial.evidence_handle, reused.evidence_handle)
        self.assertIsNotNone(initial.evidence_handle)
        self.assertNotIn("/", initial.evidence_handle)
        self.assertNotEqual(initial.evidence_handle, str(root / "runtime-root"))
        self.assertEqual(initial.evidence, reused.evidence)
        self.assertEqual(runner.invocations, invocations_before_reuse)

    def test_tampered_or_cross_task_handle_stops_before_reacquisition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")
            runtime, runner = self.make_runtime(root)
            initial = self.prepare_local_evidence(runtime, source)

            fresh_runtime, fresh_runner = self.make_runtime(root)
            rejected = fresh_runtime.prepare(
                {"sources": [str(source)]}, prior_evidence=initial
            )

            changed_controls = runtime.prepare(
                {"sources": [str(source)], "detail": "balanced"},
                prior_evidence={"evidence_handle": initial.evidence_handle},
            )
            calls_before_unhandled_follow_up = list(runner.invocations)
            unhandled_follow_up = runtime.prepare(
                {"sources": [str(source)], "question": "What changed?"}
            )

        self.assertEqual(rejected.state, "stopped")
        self.assertEqual(rejected.failure.category, "invalid_evidence_handle")
        self.assertEqual(fresh_runner.invocations, [])
        self.assertEqual(changed_controls.state, "stopped")
        self.assertEqual(changed_controls.failure.category, "reuse_requires_approval")
        self.assertEqual(changed_controls.disposition.disposal_state, "retained")
        self.assertEqual(changed_controls.disposition.reuse_state, "same_task_evidence")
        self.assertEqual(
            changed_controls.to_dict()["reuse_state"], "same_task_evidence"
        )
        self.assertEqual(changed_controls.workspace_id, initial.workspace_id)
        self.assertEqual(changed_controls.evidence_handle, initial.evidence_handle)
        self.assertIn(initial.workspace_id, changed_controls.report_markdown)
        self.assertEqual(unhandled_follow_up.state, "stopped")
        self.assertEqual(
            unhandled_follow_up.failure.category, "reuse_requires_approval"
        )
        self.assertEqual(runner.invocations, calls_before_unhandled_follow_up)

    def test_cleanup_is_explicit_and_removes_only_the_validated_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")
            output_dir = root / "user-output"
            output_dir.mkdir()
            retained_export = output_dir / "keep.txt"
            retained_export.write_text("user-owned export", encoding="utf-8")
            runtime, _ = self.make_runtime(root)

            initial = runtime.prepare(
                {
                    "sources": [str(source)],
                    "detail": "transcript",
                    "output_dir": str(output_dir),
                }
            )
            workspace = root / "runtime-root" / initial.workspace_id
            self.assertTrue(workspace.is_dir())
            self.assertTrue((workspace / ".codex-watch-workspace.json").is_file())
            self.assertTrue((workspace / ".codex-watch-manifest.jsonl").is_file())
            self.assertTrue((workspace / ".codex-watch.lock").is_file())
            record = runtime._workspaces[initial.workspace_id]
            artifact = record.path / "runtime-report.txt"
            artifact.write_text("runtime-owned report", encoding="utf-8")
            runtime._record_workspace_artifact(record, artifact, "report")
            manifest = [
                json.loads(line)
                for line in (workspace / ".codex-watch-manifest.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(manifest[-1]["disposition"], "retained")

            cleaned = runtime.cleanup("current")
            self.assertEqual(cleaned.state, "cleanup_incomplete")
            self.assertTrue(workspace.is_dir())
            self.assertTrue((workspace / "runtime-report.txt").is_file())
            self.assertTrue((workspace / ".codex-watch-workspace.json").is_file())
            runtime.close()
            for child in workspace.iterdir():
                child.unlink()
            workspace.rmdir()
            repeated = runtime.cleanup(initial.workspace_id)
            disposed = runtime.prepare(
                {"sources": [str(source)]}, prior_evidence=initial
            )
            self.assertEqual(cleaned.disposition.reuse_state, "revoked")
            self.assertFalse(workspace.exists())
            self.assertTrue(source.exists())
            self.assertEqual(
                retained_export.read_text(encoding="utf-8"), "user-owned export"
            )
            self.assertEqual(repeated.state, "cleanup_already_absent")
            self.assertEqual(disposed.state, "stopped")
            self.assertEqual(disposed.failure.category, "evidence_disposed")

    def test_cleanup_deferred_preserves_reuse_until_the_competing_lock_releases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")
            runtime, _ = self.make_runtime(root)
            initial = self.prepare_local_evidence(runtime, source)
            workspace = root / "runtime-root" / initial.workspace_id
            record = runtime._workspaces[initial.workspace_id]

            fcntl.flock(record.lock_file.fileno(), fcntl.LOCK_UN)
            with (workspace / ".codex-watch.lock").open("r+", encoding="utf-8") as rival:
                fcntl.flock(rival.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                deferred = runtime.cleanup("current")
                self.assertEqual(deferred.state, "cleanup_deferred")
                self.assertTrue(workspace.exists())
            fcntl.flock(record.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            reused = runtime.prepare(
                {"sources": [str(source)]}, prior_evidence=initial
            )

        self.assertEqual(reused.evidence_handle, initial.evidence_handle)
        self.assertEqual(reused.disposition.reuse_state, "same_task_evidence")

    def test_cleanup_refuses_unknown_altered_symlinked_and_unlocked_targets(self) -> None:
        cases = ("unknown", "altered", "symlinked", "hardlinked", "unlocked")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "user-video.mp4"
                source.write_bytes(b"user-owned fixture")
                runtime, _ = self.make_runtime(root)
                initial = self.prepare_local_evidence(runtime, source)
                workspace = root / "runtime-root" / initial.workspace_id

                if case == "unknown":
                    selector = str(source)
                elif case == "altered":
                    with (workspace / ".codex-watch-manifest.jsonl").open(
                        "a", encoding="utf-8"
                    ) as manifest:
                        manifest.write('{"unexpected":"entry"}\n')
                    selector = "current"
                elif case == "symlinked":
                    (workspace / "unowned-link").symlink_to(source)
                    selector = "current"
                elif case == "hardlinked":
                    os.link(
                        workspace / ".codex-watch-workspace.json",
                        root / "unexpected-marker-link",
                    )
                    selector = "current"
                else:
                    (workspace / ".codex-watch.lock").unlink()
                    selector = "current"

                result = runtime.cleanup(selector)

                self.assertEqual(result.state, "cleanup_refused")
                self.assertTrue(workspace.exists())
                self.assertTrue(source.exists())
                if case == "unknown":
                    still_reusable = runtime.prepare(
                        {"sources": [str(source)]}, prior_evidence=initial
                    )
                    self.assertIsNone(still_reusable.failure)
                else:
                    rejected_reuse = runtime.prepare(
                        {"sources": [str(source)]}, prior_evidence=initial
                    )
                    self.assertEqual(rejected_reuse.state, "stopped")
                    self.assertEqual(rejected_reuse.failure.category, "evidence_disposed")

    def test_cleanup_refuses_workspace_and_ancestor_symlink_replacements(self) -> None:
        with self.subTest(case="workspace"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")
            runtime, _ = self.make_runtime(root)
            initial = self.prepare_local_evidence(runtime, source)
            workspace = root / "runtime-root" / initial.workspace_id
            preserved = root / "preserved-workspace"
            workspace.rename(preserved)
            workspace.symlink_to(root / "missing-workspace", target_is_directory=True)

            refused = runtime.cleanup("current")

            self.assertEqual(refused.state, "cleanup_refused")
            self.assertTrue(workspace.is_symlink())
            self.assertTrue(preserved.exists())

        with self.subTest(case="ancestor"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            container = root / "container"
            container.mkdir()
            source = container / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")
            runtime, _ = self.make_runtime(container)
            initial = self.prepare_local_evidence(runtime, source)
            workspace = container / "runtime-root" / initial.workspace_id
            moved_container = root / "moved-container"
            container.rename(moved_container)
            container.symlink_to(moved_container, target_is_directory=True)

            refused = runtime.cleanup("current")

            self.assertEqual(refused.state, "cleanup_refused")
            self.assertTrue(workspace.exists())
            self.assertTrue(
                (moved_container / "runtime-root" / initial.workspace_id).exists()
            )

    def test_cleanup_refuses_a_renamed_workspace_even_when_its_old_path_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")
            runtime, _ = self.make_runtime(root)
            initial = self.prepare_local_evidence(runtime, source)
            workspace = root / "runtime-root" / initial.workspace_id
            moved_workspace = root / "moved-workspace"
            workspace.rename(moved_workspace)

            result = runtime.cleanup("current")

            self.assertEqual(result.state, "cleanup_refused")
            self.assertTrue(moved_workspace.is_dir())
            self.assertEqual(
                runtime.prepare(
                    {"sources": [str(source)]}, prior_evidence=initial
                ).failure.category,
                "evidence_disposed",
            )

    def test_cleanup_never_follows_a_workspace_swap_after_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")
            runtime, _ = self.make_runtime(root)
            initial = self.prepare_local_evidence(runtime, source)
            workspace = root / "runtime-root" / initial.workspace_id
            record = runtime._workspaces[initial.workspace_id]
            artifact = record.path / "report.txt"
            artifact.write_text("runtime-owned report", encoding="utf-8")
            runtime._record_workspace_artifact(record, artifact, "report")
            victim_directory = root / "user-owned-directory"
            victim_directory.mkdir()
            victim = victim_directory / "report.txt"
            victim.write_text("do not delete", encoding="utf-8")
            moved_artifact = root / "moved-runtime-report.txt"
            original_validate = runtime._workspace_validation_error_at_fd
            swapped = False

            def swap_after_validation(*args: object, **kwargs: object) -> str | None:
                nonlocal swapped
                result = original_validate(*args, **kwargs)
                if result is None and not swapped:
                    swapped = True
                    artifact.rename(moved_artifact)
                    os.link(victim, artifact)
                return result

            with patch.object(
                runtime,
                "_workspace_validation_error_at_fd",
                side_effect=swap_after_validation,
            ):
                result = runtime.cleanup("current")

            self.assertTrue(swapped)
            self.assertEqual(result.state, "cleanup_incomplete")
            self.assertEqual(victim.read_text(encoding="utf-8"), "do not delete")
            self.assertTrue(workspace.is_dir())
            self.assertEqual(artifact.read_text(encoding="utf-8"), "do not delete")
            self.assertEqual(
                moved_artifact.read_text(encoding="utf-8"), "runtime-owned report"
            )

    def test_cleanup_refuses_to_name_remove_after_an_anchored_workspace_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")
            runtime, _ = self.make_runtime(root)
            initial = self.prepare_local_evidence(runtime, source)
            workspace = root / "runtime-root" / initial.workspace_id
            record = runtime._workspaces[initial.workspace_id]
            artifact = record.path / "report.txt"
            artifact.write_text("runtime-owned report", encoding="utf-8")
            runtime._record_workspace_artifact(record, artifact, "report")
            def must_not_name_remove(
                name: object, *args: object, **kwargs: object
            ) -> None:
                self.fail("cleanup must not name-remove an anchored workspace")

            with patch.object(os, "rmdir", must_not_name_remove):
                result = runtime.cleanup("current")

            self.assertEqual(result.state, "cleanup_incomplete")
            self.assertTrue(workspace.is_dir())
            self.assertTrue((workspace / "report.txt").is_file())

    def test_workspace_creation_failure_leaves_unpublished_files_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")
            runtime, _ = self.make_runtime(root)

            with patch.object(
                watch_evidence,
                "_write_new_json_line_at",
                side_effect=OSError("synthetic manifest failure"),
            ):
                outcome = self.prepare_local_evidence(runtime, source)
            root_children = list((root / "runtime-root").iterdir())
            marker_retained = (
                len(root_children) == 1
                and (root_children[0] / ".codex-watch-workspace.json").exists()
            )

        self.assertEqual(outcome.state, "failed")
        self.assertEqual(outcome.failure.category, "workspace_creation")
        self.assertEqual(len(root_children), 1)
        self.assertTrue(marker_retained)

    def test_workspace_controls_remain_on_the_anchored_directory_after_a_name_swap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")
            user_directory = root / "user-directory"
            user_directory.mkdir()
            runtime, _ = self.make_runtime(root)
            original_write = watch_evidence._write_new_bytes_at
            preserved_workspace = root / "preserved-workspace"
            swapped = False

            def swap_before_control_write(
                directory_fd: int, name: str, value: bytes
            ) -> os.stat_result:
                nonlocal swapped
                if name == ".codex-watch-workspace.json" and not swapped:
                    swapped = True
                    workspace = next((root / "runtime-root").iterdir())
                    workspace.rename(preserved_workspace)
                    workspace.symlink_to(user_directory, target_is_directory=True)
                return original_write(directory_fd, name, value)

            with patch.object(
                watch_evidence,
                "_write_new_bytes_at",
                side_effect=swap_before_control_write,
            ):
                outcome = self.prepare_local_evidence(runtime, source)

            self.assertTrue(swapped)
            self.assertIsNone(outcome.evidence_handle)
            self.assertEqual(list(user_directory.iterdir()), [])
            self.assertTrue(
                (preserved_workspace / ".codex-watch-workspace.json").is_file()
            )
            self.assertTrue(
                (preserved_workspace / ".codex-watch-manifest.jsonl").is_file()
            )
            self.assertTrue((preserved_workspace / ".codex-watch.lock").is_file())

    def test_workspace_root_refuses_a_configured_ancestor_symlink_before_creation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")
            user_directory = root / "user-directory"
            user_directory.mkdir()
            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(user_directory, target_is_directory=True)
            runner = LifecycleRunner()
            runtime = WatchEvidenceRuntime(
                command_runner=runner,
                find_executable=lambda name: f"/fixture/{name}",
                artifact_root=linked_parent / "runtime-root",
            )

            outcome = self.prepare_local_evidence(runtime, source)

            self.assertEqual(outcome.state, "failed")
            self.assertEqual(outcome.failure.category, "workspace_creation")
            self.assertFalse((user_directory / "runtime-root").exists())

    def test_workspace_root_open_refuses_a_symlink_swap_before_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")
            runtime_root = root / "runtime-root"
            preserved_root = root / "preserved-runtime-root"
            user_directory = root / "user-directory"
            user_directory.mkdir()
            runtime, _ = self.make_runtime(root)
            original_open = os.open
            swapped = False

            def swap_before_root_open(
                name: object, *args: object, **kwargs: object
            ) -> int:
                nonlocal swapped
                if (
                    name == "runtime-root"
                    and kwargs.get("dir_fd") is not None
                    and runtime_root.exists()
                    and not swapped
                ):
                    swapped = True
                    runtime_root.rename(preserved_root)
                    runtime_root.symlink_to(user_directory, target_is_directory=True)
                return original_open(name, *args, **kwargs)

            with patch.object(os, "open", side_effect=swap_before_root_open):
                outcome = self.prepare_local_evidence(runtime, source)

            self.assertTrue(swapped)
            self.assertEqual(outcome.state, "failed")
            self.assertEqual(outcome.failure.category, "workspace_creation")
            self.assertTrue(runtime_root.is_symlink())
            self.assertEqual(list(user_directory.iterdir()), [])
            self.assertEqual(list(preserved_root.iterdir()), [])

    def test_workspace_root_open_refuses_a_directory_swap_before_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")
            runtime_root = root / "runtime-root"
            preserved_root = root / "preserved-runtime-root"
            user_directory = root / "user-directory"
            user_directory.mkdir()
            runtime, _ = self.make_runtime(root)
            original_open = os.open
            swapped = False

            def swap_before_root_open(
                name: object, *args: object, **kwargs: object
            ) -> int:
                nonlocal swapped
                if (
                    name == "runtime-root"
                    and kwargs.get("dir_fd") is not None
                    and runtime_root.exists()
                    and not swapped
                ):
                    swapped = True
                    runtime_root.rename(preserved_root)
                    user_directory.rename(runtime_root)
                return original_open(name, *args, **kwargs)

            with patch.object(os, "open", side_effect=swap_before_root_open):
                outcome = self.prepare_local_evidence(runtime, source)

            self.assertTrue(swapped)
            self.assertEqual(outcome.state, "failed")
            self.assertEqual(outcome.failure.category, "workspace_creation")
            self.assertTrue(runtime_root.is_dir())
            self.assertEqual(list(runtime_root.iterdir()), [])
            self.assertEqual(list(preserved_root.iterdir()), [])

    def test_close_is_idempotent_when_a_closed_workspace_fd_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")
            runtime, _ = self.make_runtime(root)
            initial = self.prepare_local_evidence(runtime, source)
            record = runtime._workspaces[initial.workspace_id]
            closed_workspace_fd = record.directory_fd
            self.assertIsNotNone(closed_workspace_fd)

            runtime.close()
            self.assertIsNone(record.directory_fd)
            replacement_fds: list[int] = []
            try:
                for _ in range(64):
                    replacement_fd = os.open(source, os.O_RDONLY)
                    replacement_fds.append(replacement_fd)
                    if replacement_fd == closed_workspace_fd:
                        break
                else:
                    self.fail("The test could not reuse the closed workspace descriptor.")

                runtime.close()
                os.fstat(replacement_fd)
            finally:
                for replacement_fd in replacement_fds:
                    os.close(replacement_fd)

    def test_interrupted_manifest_only_cleanup_revokes_reuse_and_keeps_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "user-video.mp4"
            source.write_bytes(b"user-owned fixture")
            runtime, _ = self.make_runtime(root)
            initial = self.prepare_local_evidence(runtime, source)
            workspace = root / "runtime-root" / initial.workspace_id
            original_unlink = os.unlink

            def fail_for_manifest(
                name: object, *args: object, **kwargs: object
            ) -> None:
                if name == ".codex-watch-manifest.jsonl":
                    raise OSError("synthetic deletion interruption")
                original_unlink(name, *args, **kwargs)

            with patch.object(os, "unlink", fail_for_manifest):
                result = runtime.cleanup("current")
            disposed = runtime.prepare(
                {"sources": [str(source)]}, prior_evidence=initial
            )
            self.assertEqual(result.state, "cleanup_incomplete")
            self.assertTrue(workspace.exists())
            self.assertEqual(disposed.state, "stopped")
            self.assertEqual(disposed.failure.category, "evidence_disposed")


if __name__ == "__main__":
    unittest.main()
