from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import fcntl
import os
from pathlib import Path
import secrets
import stat
import sys
from typing import Callable, Iterator

from toc.atomic_exchange import atomic_exchange_names


PathIdentity = tuple[int, int]
EntryIdentity = tuple[int, int, int]
_CLEANUP_DIRECTORY_NONCE = secrets.token_hex(16)


class RunRootBindingError(ValueError):
    """The lexical run path no longer names the pinned directory inode."""


@dataclass
class _RunRootBindingLifetime:
    active: bool = True


@dataclass(frozen=True)
class RunRootBinding:
    lexical_root: str
    identity: PathIdentity
    descriptor: int
    _lifetime: _RunRootBindingLifetime = field(
        default_factory=_RunRootBindingLifetime,
        compare=False,
        repr=False,
    )


_ACTIVE_RUN_ROOT: ContextVar[RunRootBinding | None] = ContextVar(
    "toc_active_run_root",
    default=None,
)


def _lexical_root(path: Path) -> str:
    return os.path.abspath(os.fspath(path))


def current_run_root_binding() -> RunRootBinding | None:
    return _ACTIVE_RUN_ROOT.get()


def require_live_run_root_binding(
    binding: RunRootBinding,
) -> RunRootBinding:
    """Reject a binding after its owning context has ended, even after FD reuse."""

    if not binding._lifetime.active:
        raise RunRootBindingError(
            f"bound run lifetime ended: {binding.lexical_root}"
        )
    try:
        opened = os.fstat(binding.descriptor)
    except OSError as exc:
        raise RunRootBindingError(
            f"bound run descriptor is unavailable: {binding.lexical_root}"
        ) from exc
    if (
        not binding._lifetime.active
        or not stat.S_ISDIR(opened.st_mode)
        or (opened.st_dev, opened.st_ino) != binding.identity
    ):
        raise RunRootBindingError(
            f"bound run descriptor identity changed: {binding.lexical_root}"
        )
    return binding


def verify_run_root(
    run_dir: Path,
    *,
    expected_identity: PathIdentity,
) -> None:
    """Verify a lexical run entry without following a replacement symlink."""

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise RunRootBindingError(
            "run-root binding requires no-follow directory opens"
        )
    descriptor = -1
    try:
        named = os.stat(run_dir, follow_symlinks=False)
        if not stat.S_ISDIR(named.st_mode):
            raise RunRootBindingError(
                f"bound run root is not a real directory: {run_dir}"
            )
        descriptor = os.open(
            run_dir,
            os.O_RDONLY
            | directory
            | nofollow
            | getattr(os, "O_CLOEXEC", 0),
        )
        opened = os.fstat(descriptor)
        actual_identity = opened.st_dev, opened.st_ino
        named_identity = named.st_dev, named.st_ino
        if (
            actual_identity != expected_identity
            or named_identity != expected_identity
        ):
            raise RunRootBindingError(
                f"bound run directory identity changed: {run_dir}"
            )
    except RunRootBindingError:
        raise
    except OSError as exc:
        raise RunRootBindingError(
            f"bound run root is unavailable: {run_dir}"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def require_bound_run_root(run_dir: Path) -> RunRootBinding | None:
    """Verify the active binding when one is present in this execution context."""

    binding = current_run_root_binding()
    if binding is None:
        return None
    if _lexical_root(run_dir) != binding.lexical_root:
        raise RunRootBindingError(
            "run operation escaped the active bound run root: "
            f"{run_dir} != {binding.lexical_root}"
        )
    require_live_run_root_binding(binding)
    verify_run_root(
        Path(binding.lexical_root),
        expected_identity=binding.identity,
    )
    require_live_run_root_binding(binding)
    return binding


def _run_file_path(run_dir: Path, path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    lexical_root = Path(run_dir)
    if not lexical_root.is_absolute():
        try:
            candidate.relative_to(lexical_root)
        except ValueError:
            pass
        else:
            # Callers commonly already hold ``run_dir / relative_path``.
            # Treat that as a run-qualified path instead of prefixing the
            # relative run root a second time.
            return candidate
    return lexical_root / candidate


def _bound_run_file(
    run_dir: Path,
    path: str | Path,
) -> tuple[RunRootBinding, Path] | None:
    """Return the active binding and a validated run-relative artifact path."""

    binding = require_bound_run_root(Path(run_dir))
    if binding is None:
        return None
    lexical_path = Path(
        os.path.abspath(os.fspath(_run_file_path(run_dir, path)))
    )
    try:
        relative = lexical_path.relative_to(binding.lexical_root)
    except ValueError as exc:
        raise RunRootBindingError(
            "run artifact escaped the active bound run root: "
            f"{lexical_path} != {binding.lexical_root}"
        ) from exc
    if (
        not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError("run artifact path must name a safe relative entry")
    return binding, relative


def _directory_open_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise RunRootBindingError(
            "bound run I/O requires no-follow directory opens"
        )
    return (
        os.O_RDONLY
        | directory
        | nofollow
        | getattr(os, "O_CLOEXEC", 0)
    )


def _duplicate_bound_root(binding: RunRootBinding) -> int:
    require_live_run_root_binding(binding)
    descriptor = -1
    try:
        descriptor = os.dup(binding.descriptor)
        opened = os.fstat(descriptor)
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise RunRootBindingError(
            f"bound run descriptor is unavailable: {binding.lexical_root}"
        ) from exc
    if (
        not binding._lifetime.active
        or not stat.S_ISDIR(opened.st_mode)
        or (opened.st_dev, opened.st_ino) != binding.identity
    ):
        os.close(descriptor)
        raise RunRootBindingError(
            f"bound run descriptor identity changed: {binding.lexical_root}"
        )
    return descriptor


def _open_bound_parent(
    binding: RunRootBinding,
    relative: Path,
    *,
    create: bool,
) -> tuple[int, str, tuple[tuple[str, PathIdentity], ...]]:
    """Open a target parent from the retained root without following links."""

    parent_descriptor = _duplicate_bound_root(binding)
    flags = _directory_open_flags()
    ancestry: list[tuple[str, PathIdentity]] = []
    try:
        for component in relative.parts[:-1]:
            child_descriptor = -1
            try:
                try:
                    child_descriptor = os.open(
                        component,
                        flags,
                        dir_fd=parent_descriptor,
                    )
                except FileNotFoundError:
                    if not create:
                        raise
                    try:
                        os.mkdir(
                            component,
                            0o755,
                            dir_fd=parent_descriptor,
                        )
                        os.fsync(parent_descriptor)
                    except FileExistsError:
                        pass
                    child_descriptor = os.open(
                        component,
                        flags,
                        dir_fd=parent_descriptor,
                    )
                opened = os.fstat(child_descriptor)
                named = os.stat(
                    component,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                if (
                    not stat.S_ISDIR(opened.st_mode)
                    or not stat.S_ISDIR(named.st_mode)
                    or (opened.st_dev, opened.st_ino)
                    != (named.st_dev, named.st_ino)
                ):
                    raise RunRootBindingError(
                        "bound run artifact directory identity changed: "
                        f"{relative}"
                    )
                ancestry.append(
                    (component, (opened.st_dev, opened.st_ino))
                )
            except Exception:
                if child_descriptor >= 0:
                    os.close(child_descriptor)
                raise
            os.close(parent_descriptor)
            parent_descriptor = child_descriptor
        return parent_descriptor, relative.parts[-1], tuple(ancestry)
    except Exception:
        os.close(parent_descriptor)
        raise


def _verify_bound_parent_ancestry(
    binding: RunRootBinding,
    relative: Path,
    ancestry: tuple[tuple[str, PathIdentity], ...],
) -> None:
    """Rewalk a parent chain so an ABA directory swap cannot select data."""

    parent_descriptor = _duplicate_bound_root(binding)
    flags = _directory_open_flags()
    try:
        for component, expected_identity in ancestry:
            child_descriptor = -1
            try:
                child_descriptor = os.open(
                    component,
                    flags,
                    dir_fd=parent_descriptor,
                )
                opened = os.fstat(child_descriptor)
                named = os.stat(
                    component,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                if (
                    not stat.S_ISDIR(opened.st_mode)
                    or not stat.S_ISDIR(named.st_mode)
                    or (opened.st_dev, opened.st_ino)
                    != expected_identity
                    or (named.st_dev, named.st_ino)
                    != expected_identity
                ):
                    raise RunRootBindingError(
                        "bound run artifact ancestry changed: "
                        f"{relative}"
                    )
            except Exception:
                if child_descriptor >= 0:
                    os.close(child_descriptor)
                raise
            os.close(parent_descriptor)
            parent_descriptor = child_descriptor
    finally:
        _run_cleanup_actions(
            sys.exception(),
            [
                (
                    "closing bound ancestry verification descriptor",
                    lambda: os.close(parent_descriptor),
                )
            ],
        )


def _assert_named_regular_identity(
    descriptor: int,
    parent_descriptor: int,
    name: str,
    *,
    expected_identity: PathIdentity,
    require_single_link: bool,
) -> os.stat_result:
    opened = os.fstat(descriptor)
    named = os.stat(
        name,
        dir_fd=parent_descriptor,
        follow_symlinks=False,
    )
    if (
        not stat.S_ISREG(opened.st_mode)
        or not stat.S_ISREG(named.st_mode)
        or (opened.st_dev, opened.st_ino) != expected_identity
        or (named.st_dev, named.st_ino) != expected_identity
        or (
            require_single_link
            and (opened.st_nlink != 1 or named.st_nlink != 1)
        )
    ):
        raise RunRootBindingError(
            f"bound run artifact identity changed: {name}"
        )
    return opened


def _entry_identity(value: os.stat_result) -> EntryIdentity:
    return value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode)


def _note_cleanup_error(
    primary: BaseException | None,
    *,
    label: str,
    error: BaseException,
) -> None:
    """Preserve an in-flight operation error when integrity cleanup also fails."""

    if primary is None:
        raise error
    add_note = getattr(primary, "add_note", None)
    if callable(add_note):
        add_note(f"{label} also failed: {type(error).__name__}: {error}")


def _run_cleanup_action(
    primary: BaseException | None,
    *,
    label: str,
    action: object,
) -> None:
    try:
        action()  # type: ignore[operator]
    except BaseException as error:
        _note_cleanup_error(primary, label=label, error=error)


def _run_cleanup_actions(
    primary: BaseException | None,
    actions: list[tuple[str, Callable[[], object]]],
) -> None:
    errors: list[tuple[str, BaseException]] = []
    for label, action in actions:
        try:
            action()
        except BaseException as error:
            errors.append((label, error))
    if not errors:
        return
    if primary is not None:
        add_note = getattr(primary, "add_note", None)
        if callable(add_note):
            for label, error in errors:
                add_note(
                    f"{label} also failed: "
                    f"{type(error).__name__}: {error}"
                )
        return
    label, error = errors[0]
    add_note = getattr(error, "add_note", None)
    if callable(add_note):
        for extra_label, extra_error in errors[1:]:
            add_note(
                f"{extra_label} also failed: "
                f"{type(extra_error).__name__}: {extra_error}"
            )
    raise error


def _open_private_cleanup_directory(parent_descriptor: int) -> int:
    """Open the process-private namespace used before deleting a verified name."""

    directory_name = (
        f".toc-bound-cleanup-{os.getpid()}-{_CLEANUP_DIRECTORY_NONCE}"
    )
    created = False
    try:
        os.mkdir(directory_name, 0o700, dir_fd=parent_descriptor)
        created = True
        os.fsync(parent_descriptor)
    except FileExistsError:
        pass
    descriptor = -1
    try:
        descriptor = os.open(
            directory_name,
            _directory_open_flags(),
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(descriptor)
        named = os.stat(
            directory_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(opened.st_mode)
            or _entry_identity(opened) != _entry_identity(named)
            or opened.st_uid != os.geteuid()
        ):
            raise RunRootBindingError("bound cleanup directory is unsafe")
        if created:
            os.fchmod(descriptor, 0o700)
            opened = os.fstat(descriptor)
        if stat.S_IMODE(opened.st_mode) != 0o700:
            raise RunRootBindingError(
                "bound cleanup directory must be owner-only"
            )
        return descriptor
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        raise


def _stat_entry_identity(
    parent_descriptor: int,
    name: str,
) -> EntryIdentity | None:
    try:
        return _entry_identity(
            os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        )
    except FileNotFoundError:
        return None


def _exchange_names_reconciled(
    source_descriptor: int,
    source_name: str,
    destination_descriptor: int,
    destination_name: str,
    *,
    source_identity: EntryIdentity,
    destination_identity: EntryIdentity,
) -> None:
    """Exchange two verified names and reconcile an error-after-syscall hook."""

    if (
        _stat_entry_identity(source_descriptor, source_name)
        != source_identity
        or _stat_entry_identity(destination_descriptor, destination_name)
        != destination_identity
    ):
        raise RunRootBindingError(
            f"bound exchange input identity changed: "
            f"{source_name} <-> {destination_name}"
        )
    try:
        atomic_exchange_names(
            source_descriptor,
            source_name,
            destination_descriptor,
            destination_name,
        )
    except BaseException as exchange_error:
        source_now = _stat_entry_identity(source_descriptor, source_name)
        destination_now = _stat_entry_identity(
            destination_descriptor,
            destination_name,
        )
        if (
            source_now == destination_identity
            and destination_now == source_identity
        ):
            return
        if destination_now == source_identity and source_now is not None:
            try:
                atomic_exchange_names(
                    source_descriptor,
                    source_name,
                    destination_descriptor,
                    destination_name,
                )
            except BaseException as rollback_error:
                add_note = getattr(exchange_error, "add_note", None)
                if callable(add_note):
                    add_note(
                        "bound exchange rollback also failed: "
                        f"{type(rollback_error).__name__}: {rollback_error}"
                    )
        raise
    source_now = _stat_entry_identity(source_descriptor, source_name)
    destination_now = _stat_entry_identity(
        destination_descriptor,
        destination_name,
    )
    if (
        source_now != destination_identity
        or destination_now != source_identity
    ):
        # If our published inode is still at the destination, the unexpected
        # source is a leaf substitution that the exchange moved aside.  Swap
        # it back instead of deleting or stranding the substituted entry.
        if destination_now == source_identity and source_now is not None:
            try:
                atomic_exchange_names(
                    source_descriptor,
                    source_name,
                    destination_descriptor,
                    destination_name,
                )
            except BaseException as rollback_error:
                failure = RunRootBindingError(
                    f"bound exchange result changed and rollback failed: "
                    f"{source_name} <-> {destination_name}"
                )
                failure.add_note(
                    f"rollback failure: {type(rollback_error).__name__}: "
                    f"{rollback_error}"
                )
                raise failure from rollback_error
        raise RunRootBindingError(
            f"bound exchange result identity changed: "
            f"{source_name} <-> {destination_name}"
        )


def _rollback_exchange_if_exact(
    source_descriptor: int,
    source_name: str,
    destination_descriptor: int,
    destination_name: str,
    *,
    source_identity: EntryIdentity,
    destination_identity: EntryIdentity,
) -> bool:
    """Undo an exchange only while both public names still match our result."""

    if (
        _stat_entry_identity(source_descriptor, source_name)
        != destination_identity
        or _stat_entry_identity(destination_descriptor, destination_name)
        != source_identity
    ):
        return False
    _exchange_names_reconciled(
        source_descriptor,
        source_name,
        destination_descriptor,
        destination_name,
        source_identity=destination_identity,
        destination_identity=source_identity,
    )
    return True


def _remove_name_if_identity(
    parent_descriptor: int,
    name: str,
    *,
    expected_identity: EntryIdentity,
) -> bool:
    """Remove only the named inode that was verified by the caller.

    The public entry is first exchanged with an owned placeholder.  A racing
    replacement is therefore restored instead of being passed to ``unlink``.
    Actual deletion happens only under an owner-only, unpredictable cleanup
    namespace.
    """

    if _stat_entry_identity(parent_descriptor, name) != expected_identity:
        return False
    cleanup_descriptor = _open_private_cleanup_directory(parent_descriptor)
    placeholder_name = f"placeholder-{secrets.token_hex(16)}"
    trash_name = f"trash-{secrets.token_hex(16)}"
    placeholder_descriptor = -1
    placeholder_identity: EntryIdentity | None = None
    exchanged = False
    public_detached = False
    try:
        placeholder_descriptor = os.open(
            placeholder_name,
            os.O_RDWR
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            0o600,
            dir_fd=cleanup_descriptor,
        )
        placeholder = os.fstat(placeholder_descriptor)
        placeholder_identity = _entry_identity(placeholder)
        if not stat.S_ISREG(placeholder.st_mode) or placeholder.st_nlink != 1:
            raise RunRootBindingError(
                f"bound cleanup placeholder is unsafe: {name}"
            )

        _exchange_names_reconciled(
            parent_descriptor,
            name,
            cleanup_descriptor,
            placeholder_name,
            source_identity=expected_identity,
            destination_identity=placeholder_identity,
        )
        exchanged = True

        public_now = _stat_entry_identity(parent_descriptor, name)
        quarantined_now = _stat_entry_identity(
            cleanup_descriptor,
            placeholder_name,
        )
        if (
            public_now != placeholder_identity
            or quarantined_now != expected_identity
        ):
            if (
                public_now == placeholder_identity
                and quarantined_now is not None
            ):
                _exchange_names_reconciled(
                    parent_descriptor,
                    name,
                    cleanup_descriptor,
                    placeholder_name,
                    source_identity=placeholder_identity,
                    destination_identity=quarantined_now,
                )
                exchanged = False
            return False

        # Rename (never unlink) the public placeholder, then verify what moved.
        # If a peer substituted the public name, it is moved aside and restored
        # without ever being deleted.
        os.rename(
            name,
            trash_name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=cleanup_descriptor,
        )
        moved_identity = _stat_entry_identity(cleanup_descriptor, trash_name)
        if moved_identity != placeholder_identity:
            try:
                os.link(
                    trash_name,
                    name,
                    src_dir_fd=cleanup_descriptor,
                    dst_dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except OSError:
                pass
            return False
        public_detached = True
        os.fsync(parent_descriptor)

        # These unpredictable entries live in an owner-only directory.  Check
        # their identities immediately before unlink so public substitutions
        # are never disposed as cleanup.
        if (
            _stat_entry_identity(cleanup_descriptor, placeholder_name)
            != expected_identity
            or _stat_entry_identity(cleanup_descriptor, trash_name)
            != placeholder_identity
        ):
            return False
        os.unlink(placeholder_name, dir_fd=cleanup_descriptor)
        os.unlink(trash_name, dir_fd=cleanup_descriptor)
        os.fsync(cleanup_descriptor)
        return True
    finally:
        primary = sys.exception()
        actions: list[tuple[str, Callable[[], object]]] = []
        if placeholder_descriptor >= 0:
            actions.append(
                (
                    "closing bound cleanup placeholder",
                    lambda: os.close(placeholder_descriptor),
                )
            )
        # Before exchange, a leftover placeholder is ours.  Once names have
        # moved, avoid broad best-effort unlinks that could target a substitute.
        if not exchanged and placeholder_identity is not None:
            if (
                _stat_entry_identity(cleanup_descriptor, placeholder_name)
                == placeholder_identity
            ):
                actions.append(
                    (
                        "removing unused bound cleanup placeholder",
                        lambda: os.unlink(
                            placeholder_name,
                            dir_fd=cleanup_descriptor,
                        ),
                    )
                )
        if public_detached:
            actions.append(
                (
                    "syncing bound cleanup namespace",
                    lambda: os.fsync(cleanup_descriptor),
                )
            )
        actions.append(
            (
                "closing bound cleanup directory",
                lambda: os.close(cleanup_descriptor),
            )
        )
        _run_cleanup_actions(primary, actions)


def _remove_name_or_raise(
    parent_descriptor: int,
    name: str,
    *,
    expected_identity: EntryIdentity,
) -> None:
    if not _remove_name_if_identity(
        parent_descriptor,
        name,
        expected_identity=expected_identity,
    ):
        raise RunRootBindingError(
            f"bound cleanup name identity changed: {name}"
        )


def _write_all(descriptor: int, data: bytes) -> None:
    remaining = memoryview(data)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise OSError("bound run write made no progress")
        remaining = remaining[written:]


@contextmanager
def _temporary_run_root_binding(
    run_dir: Path,
    *,
    create: bool,
) -> Iterator[RunRootBinding]:
    """Give unbound callers the same descriptor-relative safety contract."""

    if create:
        run_dir.mkdir(parents=True, exist_ok=True)
    try:
        named = os.stat(run_dir, follow_symlinks=False)
    except OSError as exc:
        raise RunRootBindingError(
            f"run root is unavailable: {run_dir}"
        ) from exc
    if not stat.S_ISDIR(named.st_mode):
        raise RunRootBindingError(
            f"run root must be a real directory: {run_dir}"
        )
    descriptor = -1
    try:
        descriptor = os.open(run_dir, _directory_open_flags())
        opened = os.fstat(descriptor)
        identity = opened.st_dev, opened.st_ino
        if identity != (named.st_dev, named.st_ino):
            raise RunRootBindingError(
                f"run root identity changed while opening: {run_dir}"
            )
        with bind_run_root(
            run_dir,
            expected_identity=identity,
            descriptor=descriptor,
        ) as binding:
            yield binding
    finally:
        primary = sys.exception()
        if descriptor >= 0:
            _run_cleanup_action(
                primary,
                label="closing temporary run-root descriptor",
                action=lambda: os.close(descriptor),
            )


def _finish_bound_parent(
    *,
    primary: BaseException | None,
    binding: RunRootBinding,
    relative: Path,
    ancestry: tuple[tuple[str, PathIdentity], ...],
    parent_descriptor: int,
) -> None:
    _run_cleanup_actions(
        primary,
        [
            (
                "verifying bound artifact parent ancestry",
                lambda: _verify_bound_parent_ancestry(
                    binding,
                    relative,
                    ancestry,
                ),
            ),
            (
                "closing bound artifact parent",
                lambda: os.close(parent_descriptor),
            ),
            (
                "verifying bound run root",
                lambda: require_bound_run_root(Path(binding.lexical_root)),
            ),
        ],
    )


def read_run_file_bytes(run_dir: Path, path: str | Path) -> bytes:
    """Read a run file; active bindings use the retained root descriptor."""

    bound = _bound_run_file(run_dir, path)
    if bound is None:
        with _temporary_run_root_binding(Path(run_dir), create=False):
            return read_run_file_bytes(run_dir, path)
    binding, relative = bound
    parent_descriptor, name, ancestry = _open_bound_parent(
        binding,
        relative,
        create=False,
    )
    descriptor = -1
    locked = False
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(descriptor)
        identity = opened.st_dev, opened.st_ino
        _assert_named_regular_identity(
            descriptor,
            parent_descriptor,
            name,
            expected_identity=identity,
            require_single_link=True,
        )
        fcntl.flock(descriptor, fcntl.LOCK_SH)
        locked = True
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        _assert_named_regular_identity(
            descriptor,
            parent_descriptor,
            name,
            expected_identity=identity,
            require_single_link=True,
        )
        return b"".join(chunks)
    finally:
        primary = sys.exception()
        actions: list[tuple[str, Callable[[], object]]] = []
        if descriptor >= 0:
            if locked:
                actions.append(
                    (
                        "unlocking bound read artifact",
                        lambda: fcntl.flock(
                            descriptor,
                            fcntl.LOCK_UN,
                        ),
                    )
                )
            actions.append(
                (
                    "closing bound read artifact",
                    lambda: os.close(descriptor),
                )
            )
        actions.extend(
            [
                (
                    "verifying bound read parent ancestry",
                    lambda: _verify_bound_parent_ancestry(
                        binding,
                        relative,
                        ancestry,
                    ),
                ),
                (
                    "closing bound read parent",
                    lambda: os.close(parent_descriptor),
                ),
                (
                    "verifying run root after bound read",
                    lambda: require_bound_run_root(
                        Path(binding.lexical_root)
                    ),
                ),
            ]
        )
        _run_cleanup_actions(primary, actions)


def run_file_entry_exists(run_dir: Path, path: str | Path) -> bool:
    """Check an exact run entry; active bindings never reopen the root path."""

    bound = _bound_run_file(run_dir, path)
    if bound is None:
        try:
            with _temporary_run_root_binding(Path(run_dir), create=False):
                return run_file_entry_exists(run_dir, path)
        except FileNotFoundError:
            return False
    binding, relative = bound
    try:
        parent_descriptor, name, ancestry = _open_bound_parent(
            binding,
            relative,
            create=False,
        )
    except FileNotFoundError:
        require_bound_run_root(Path(binding.lexical_root))
        return False
    try:
        try:
            os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return False
        return True
    finally:
        _finish_bound_parent(
            primary=sys.exception(),
            binding=binding,
            relative=relative,
            ancestry=ancestry,
            parent_descriptor=parent_descriptor,
        )


def list_run_directory_entry_names(
    run_dir: Path,
    path: str | Path,
) -> tuple[str, ...]:
    """List one exact run directory through the retained root descriptor."""

    bound = _bound_run_file(run_dir, path)
    if bound is None:
        with _temporary_run_root_binding(Path(run_dir), create=False):
            return list_run_directory_entry_names(run_dir, path)
    binding, relative = bound
    parent_descriptor, name, ancestry = _open_bound_parent(
        binding,
        relative,
        create=False,
    )
    directory_descriptor = -1
    try:
        named = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        directory_descriptor = os.open(
            name,
            _directory_open_flags(),
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(directory_descriptor)
        identity = _entry_identity(opened)
        if (
            not stat.S_ISDIR(named.st_mode)
            or not stat.S_ISDIR(opened.st_mode)
            or _entry_identity(named) != identity
        ):
            raise RunRootBindingError(
                f"bound run directory identity changed: {relative}"
            )
        entries = tuple(sorted(os.listdir(directory_descriptor)))
        opened_after = os.fstat(directory_descriptor)
        named_after = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(opened_after.st_mode)
            or not stat.S_ISDIR(named_after.st_mode)
            or _entry_identity(opened_after) != identity
            or _entry_identity(named_after) != identity
        ):
            raise RunRootBindingError(
                f"bound run directory changed while listing: {relative}"
            )
        return entries
    finally:
        primary = sys.exception()
        actions: list[tuple[str, Callable[[], object]]] = []
        if directory_descriptor >= 0:
            actions.append(
                (
                    "closing listed bound run directory",
                    lambda: os.close(directory_descriptor),
                )
            )
        actions.extend(
            [
                (
                    "verifying listed bound directory ancestry",
                    lambda: _verify_bound_parent_ancestry(
                        binding,
                        relative,
                        ancestry,
                    ),
                ),
                (
                    "closing listed bound directory parent",
                    lambda: os.close(parent_descriptor),
                ),
                (
                    "verifying run root after directory listing",
                    lambda: require_bound_run_root(
                        Path(binding.lexical_root)
                    ),
                ),
            ]
        )
        _run_cleanup_actions(primary, actions)


def _stable_regular_file_identity(
    value: os.stat_result,
) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        stat.S_IFMT(value.st_mode),
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def read_run_directory_regular_files(
    run_dir: Path,
    path: str | Path,
    *,
    suffix: str | None = None,
) -> tuple[tuple[str, bytes], ...]:
    """Read a stable set of regular files through one retained directory FD."""

    if suffix is not None and ("/" in suffix or "\\" in suffix):
        raise ValueError("directory read suffix must not contain separators")
    bound = _bound_run_file(run_dir, path)
    if bound is None:
        with _temporary_run_root_binding(Path(run_dir), create=False):
            return read_run_directory_regular_files(
                run_dir,
                path,
                suffix=suffix,
            )
    binding, relative = bound
    parent_descriptor, name, ancestry = _open_bound_parent(
        binding,
        relative,
        create=False,
    )
    directory_descriptor = -1
    try:
        named_directory = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        directory_descriptor = os.open(
            name,
            _directory_open_flags(),
            dir_fd=parent_descriptor,
        )
        opened_directory = os.fstat(directory_descriptor)
        directory_identity = _entry_identity(opened_directory)
        if (
            not stat.S_ISDIR(named_directory.st_mode)
            or not stat.S_ISDIR(opened_directory.st_mode)
            or _entry_identity(named_directory) != directory_identity
        ):
            raise RunRootBindingError(
                f"bound run directory identity changed: {relative}"
            )

        def selected_names() -> tuple[str, ...]:
            return tuple(
                sorted(
                    entry
                    for entry in os.listdir(directory_descriptor)
                    if suffix is None or entry.endswith(suffix)
                )
            )

        names = selected_names()
        results: list[tuple[str, bytes]] = []
        for entry in names:
            if entry in {"", ".", ".."} or "/" in entry or "\\" in entry:
                raise RunRootBindingError(
                    f"unsafe bound directory entry name: {entry!r}"
                )
            file_descriptor = -1
            locked = False
            try:
                file_descriptor = os.open(
                    entry,
                    os.O_RDONLY
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_NONBLOCK", 0),
                    dir_fd=directory_descriptor,
                )
                opened_file = os.fstat(file_descriptor)
                named_file = os.stat(
                    entry,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
                stable_identity = _stable_regular_file_identity(opened_file)
                if (
                    not stat.S_ISREG(opened_file.st_mode)
                    or not stat.S_ISREG(named_file.st_mode)
                    or opened_file.st_nlink != 1
                    or named_file.st_nlink != 1
                    or _stable_regular_file_identity(named_file)
                    != stable_identity
                ):
                    raise RunRootBindingError(
                        f"bound directory entry is not one stable regular "
                        f"file: {relative / entry}"
                    )
                fcntl.flock(file_descriptor, fcntl.LOCK_SH)
                locked = True
                chunks: list[bytes] = []
                while chunk := os.read(file_descriptor, 1024 * 1024):
                    chunks.append(chunk)
                opened_after = os.fstat(file_descriptor)
                named_after = os.stat(
                    entry,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
                if (
                    opened_after.st_nlink != 1
                    or named_after.st_nlink != 1
                    or _stable_regular_file_identity(opened_after)
                    != stable_identity
                    or _stable_regular_file_identity(named_after)
                    != stable_identity
                ):
                    raise RunRootBindingError(
                        f"bound directory entry changed while reading: "
                        f"{relative / entry}"
                    )
                results.append((entry, b"".join(chunks)))
            finally:
                primary = sys.exception()
                actions: list[tuple[str, Callable[[], object]]] = []
                if file_descriptor >= 0:
                    if locked:
                        actions.append(
                            (
                                f"unlocking directory entry {entry}",
                                lambda fd=file_descriptor: fcntl.flock(
                                    fd,
                                    fcntl.LOCK_UN,
                                ),
                            )
                        )
                    actions.append(
                        (
                            f"closing directory entry {entry}",
                            lambda fd=file_descriptor: os.close(fd),
                        )
                    )
                _run_cleanup_actions(primary, actions)

        if selected_names() != names:
            raise RunRootBindingError(
                f"bound directory entry set changed while reading: {relative}"
            )
        opened_after = os.fstat(directory_descriptor)
        named_after = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(opened_after.st_mode)
            or not stat.S_ISDIR(named_after.st_mode)
            or _entry_identity(opened_after) != directory_identity
            or _entry_identity(named_after) != directory_identity
        ):
            raise RunRootBindingError(
                f"bound run directory changed while reading: {relative}"
            )
        return tuple(results)
    finally:
        primary = sys.exception()
        actions: list[tuple[str, Callable[[], object]]] = []
        if directory_descriptor >= 0:
            actions.append(
                (
                    "closing bound directory snapshot descriptor",
                    lambda: os.close(directory_descriptor),
                )
            )
        actions.extend(
            [
                (
                    "verifying bound directory snapshot ancestry",
                    lambda: _verify_bound_parent_ancestry(
                        binding,
                        relative,
                        ancestry,
                    ),
                ),
                (
                    "closing bound directory snapshot parent",
                    lambda: os.close(parent_descriptor),
                ),
                (
                    "verifying run root after directory snapshot",
                    lambda: require_bound_run_root(
                        Path(binding.lexical_root)
                    ),
                ),
            ]
        )
        _run_cleanup_actions(primary, actions)


def write_run_file_text(
    run_dir: Path,
    path: str | Path,
    text: str,
    *,
    encoding: str = "utf-8",
) -> Path:
    """Write text, publishing atomically and durably under an active binding."""

    target = _run_file_path(run_dir, path)
    bound = _bound_run_file(run_dir, path)
    if bound is None:
        with _temporary_run_root_binding(Path(run_dir), create=True):
            return write_run_file_text(
                run_dir,
                path,
                text,
                encoding=encoding,
            )
    binding, relative = bound
    parent_descriptor, name, ancestry = _open_bound_parent(
        binding,
        relative,
        create=True,
    )
    descriptor = -1
    temporary_name = (
        f".{name}.{os.getpid()}.{secrets.token_hex(12)}.tmp"
    )
    temporary_identity: EntryIdentity | None = None
    previous_identity: EntryIdentity | None = None
    publication_committed = False
    try:
        try:
            previous = os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            previous = None
        if previous is not None:
            if not stat.S_ISREG(previous.st_mode) or previous.st_nlink != 1:
                raise RunRootBindingError(
                    f"bound run destination is unsafe: {relative}"
                )
            previous_identity = _entry_identity(previous)

        descriptor = os.open(
            temporary_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            0o600,
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise RunRootBindingError(
                f"bound run temporary artifact is unsafe: {relative}"
            )
        temporary_identity = _entry_identity(opened)
        _write_all(descriptor, text.encode(encoding))
        os.fsync(descriptor)
        _assert_named_regular_identity(
            descriptor,
            parent_descriptor,
            temporary_name,
            expected_identity=(
                temporary_identity[0],
                temporary_identity[1],
            ),
            require_single_link=True,
        )

        if previous_identity is None:
            try:
                os.link(
                    temporary_name,
                    name,
                    src_dir_fd=parent_descriptor,
                    dst_dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise RunRootBindingError(
                    f"bound run destination appeared during publication: "
                    f"{relative}"
                ) from exc
            if (
                _stat_entry_identity(parent_descriptor, name)
                != temporary_identity
                or _stat_entry_identity(parent_descriptor, temporary_name)
                != temporary_identity
            ):
                raise RunRootBindingError(
                    f"bound run destination changed during publication: "
                    f"{relative}"
                )
        else:
            current = os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (
                _entry_identity(current) != previous_identity
                or not stat.S_ISREG(current.st_mode)
                or current.st_nlink != 1
            ):
                raise RunRootBindingError(
                    f"bound run destination identity changed: {relative}"
                )
            _exchange_names_reconciled(
                parent_descriptor,
                temporary_name,
                parent_descriptor,
                name,
                source_identity=temporary_identity,
                destination_identity=previous_identity,
            )
            destination_now = os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            old_now = os.stat(
                temporary_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (
                _entry_identity(destination_now) != temporary_identity
                or destination_now.st_nlink != 1
                or _entry_identity(old_now) != previous_identity
                or old_now.st_nlink != 1
            ):
                _rollback_exchange_if_exact(
                    parent_descriptor,
                    temporary_name,
                    parent_descriptor,
                    name,
                    source_identity=temporary_identity,
                    destination_identity=previous_identity,
                )
                raise RunRootBindingError(
                    f"bound run destination raced during publication: "
                    f"{relative}"
                )

        cleanup_identity = (
            previous_identity
            if previous_identity is not None
            else temporary_identity
        )
        if cleanup_identity is None or not _remove_name_if_identity(
            parent_descriptor,
            temporary_name,
            expected_identity=cleanup_identity,
        ):
            raise RunRootBindingError(
                f"bound run destination cleanup was not identity-safe: "
                f"{relative}"
            )
        publication_committed = True
        _assert_named_regular_identity(
            descriptor,
            parent_descriptor,
            name,
            expected_identity=(
                temporary_identity[0],
                temporary_identity[1],
            ),
            require_single_link=True,
        )
        os.fsync(parent_descriptor)
    finally:
        primary = sys.exception()
        actions: list[tuple[str, Callable[[], object]]] = []
        if descriptor >= 0:
            actions.append(
                (
                    "closing bound write artifact",
                    lambda: os.close(descriptor),
                )
            )
        if (
            not publication_committed
            and temporary_identity is not None
            and _stat_entry_identity(parent_descriptor, temporary_name)
            == temporary_identity
        ):
            actions.append(
                (
                    "removing unpublished bound write artifact",
                    lambda: _remove_name_or_raise(
                        parent_descriptor,
                        temporary_name,
                        expected_identity=temporary_identity,
                    ),
                )
            )
        actions.extend(
            [
                (
                    "verifying bound write parent ancestry",
                    lambda: _verify_bound_parent_ancestry(
                        binding,
                        relative,
                        ancestry,
                    ),
                ),
                (
                    "closing bound write parent",
                    lambda: os.close(parent_descriptor),
                ),
                (
                    "verifying run root after bound write",
                    lambda: require_bound_run_root(
                        Path(binding.lexical_root)
                    ),
                ),
            ]
        )
        _run_cleanup_actions(primary, actions)
    return target


def append_run_file_text(
    run_dir: Path,
    path: str | Path,
    text: str,
    *,
    encoding: str = "utf-8",
) -> Path:
    """Append one serialized record with copy-on-write atomic publication."""

    target = _run_file_path(run_dir, path)
    bound = _bound_run_file(run_dir, path)
    if bound is None:
        with _temporary_run_root_binding(Path(run_dir), create=True):
            return append_run_file_text(
                run_dir,
                path,
                text,
                encoding=encoding,
            )
    binding, relative = bound
    parent_descriptor, name, ancestry = _open_bound_parent(
        binding,
        relative,
        create=True,
    )
    lock_descriptor = -1
    current_descriptor = -1
    temporary_descriptor = -1
    lock_locked = False
    current_locked = False
    temporary_name = (
        f".{name}.append-{os.getpid()}-{secrets.token_hex(16)}"
    )
    temporary_identity: EntryIdentity | None = None
    previous_identity: EntryIdentity | None = None
    publication_started = False
    publication_committed = False
    try:
        lock_name = f".{name}.append.lock"
        lock_descriptor = os.open(
            lock_name,
            os.O_RDWR
            | os.O_CREAT
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            0o600,
            dir_fd=parent_descriptor,
        )
        lock_opened = os.fstat(lock_descriptor)
        lock_identity = lock_opened.st_dev, lock_opened.st_ino
        _assert_named_regular_identity(
            lock_descriptor,
            parent_descriptor,
            lock_name,
            expected_identity=lock_identity,
            require_single_link=True,
        )
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        lock_locked = True
        _assert_named_regular_identity(
            lock_descriptor,
            parent_descriptor,
            lock_name,
            expected_identity=lock_identity,
            require_single_link=True,
        )

        current_data = b""
        try:
            current_descriptor = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0),
                dir_fd=parent_descriptor,
            )
        except FileNotFoundError:
            current_descriptor = -1
        if current_descriptor >= 0:
            current_opened = os.fstat(current_descriptor)
            current_identity = (
                current_opened.st_dev,
                current_opened.st_ino,
            )
            previous_identity = _entry_identity(current_opened)
            _assert_named_regular_identity(
                current_descriptor,
                parent_descriptor,
                name,
                expected_identity=current_identity,
                require_single_link=True,
            )
            fcntl.flock(current_descriptor, fcntl.LOCK_EX)
            current_locked = True
            _assert_named_regular_identity(
                current_descriptor,
                parent_descriptor,
                name,
                expected_identity=current_identity,
                require_single_link=True,
            )
            chunks: list[bytes] = []
            while chunk := os.read(current_descriptor, 1024 * 1024):
                chunks.append(chunk)
            current_data = b"".join(chunks)
            _assert_named_regular_identity(
                current_descriptor,
                parent_descriptor,
                name,
                expected_identity=current_identity,
                require_single_link=True,
            )

        temporary_descriptor = os.open(
            temporary_name,
            os.O_RDWR
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            0o600,
            dir_fd=parent_descriptor,
        )
        temporary_opened = os.fstat(temporary_descriptor)
        temporary_identity = _entry_identity(temporary_opened)
        if (
            not stat.S_ISREG(temporary_opened.st_mode)
            or temporary_opened.st_nlink != 1
        ):
            raise RunRootBindingError(
                f"bound append temporary artifact is unsafe: {relative}"
            )
        _write_all(
            temporary_descriptor,
            current_data + text.encode(encoding),
        )
        os.fsync(temporary_descriptor)
        _assert_named_regular_identity(
            temporary_descriptor,
            parent_descriptor,
            temporary_name,
            expected_identity=(
                temporary_identity[0],
                temporary_identity[1],
            ),
            require_single_link=True,
        )

        if previous_identity is None:
            try:
                os.link(
                    temporary_name,
                    name,
                    src_dir_fd=parent_descriptor,
                    dst_dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise RunRootBindingError(
                    f"bound append target appeared during publication: "
                    f"{relative}"
                ) from exc
            publication_started = True
            if (
                _stat_entry_identity(parent_descriptor, name)
                != temporary_identity
                or _stat_entry_identity(parent_descriptor, temporary_name)
                != temporary_identity
            ):
                raise RunRootBindingError(
                    f"bound append publication identity changed: {relative}"
                )
        else:
            if (
                _stat_entry_identity(parent_descriptor, name)
                != previous_identity
            ):
                raise RunRootBindingError(
                    f"bound append target identity changed: {relative}"
                )
            _exchange_names_reconciled(
                parent_descriptor,
                temporary_name,
                parent_descriptor,
                name,
                source_identity=temporary_identity,
                destination_identity=previous_identity,
            )
            publication_started = True
            # Validate link counts through the retained descriptors.  A new
            # hardlink to the prior state triggers rollback without mutating it.
            destination_now = os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            old_now = os.stat(
                temporary_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (
                _entry_identity(destination_now) != temporary_identity
                or destination_now.st_nlink != 1
                or _entry_identity(old_now) != previous_identity
                or old_now.st_nlink != 1
            ):
                _rollback_exchange_if_exact(
                    parent_descriptor,
                    temporary_name,
                    parent_descriptor,
                    name,
                    source_identity=temporary_identity,
                    destination_identity=previous_identity,
                )
                publication_started = False
                raise RunRootBindingError(
                    f"bound append publication raced with a leaf change: "
                    f"{relative}"
                )

        cleanup_identity = (
            previous_identity
            if previous_identity is not None
            else temporary_identity
        )
        if cleanup_identity is None or not _remove_name_if_identity(
            parent_descriptor,
            temporary_name,
            expected_identity=cleanup_identity,
        ):
            raise RunRootBindingError(
                f"bound append could not safely clean its old name: "
                f"{relative}"
            )
        publication_committed = True
        final_named = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            _entry_identity(final_named) != temporary_identity
            or not stat.S_ISREG(final_named.st_mode)
            or final_named.st_nlink != 1
        ):
            raise RunRootBindingError(
                f"bound append final identity changed: {relative}"
            )
        os.fsync(parent_descriptor)
    finally:
        primary = sys.exception()
        if (
            not publication_committed
            and temporary_identity is not None
            and _stat_entry_identity(parent_descriptor, temporary_name)
            == temporary_identity
        ):
            _run_cleanup_action(
                primary,
                label="removing unpublished append temporary",
                action=lambda: _remove_name_if_identity(
                    parent_descriptor,
                    temporary_name,
                    expected_identity=temporary_identity,
                ),
            )
        if current_descriptor >= 0:
            if current_locked:
                _run_cleanup_action(
                    primary,
                    label="unlocking prior append artifact",
                    action=lambda: fcntl.flock(
                        current_descriptor,
                        fcntl.LOCK_UN,
                    ),
                )
            _run_cleanup_action(
                primary,
                label="closing prior append artifact",
                action=lambda: os.close(current_descriptor),
            )
        if temporary_descriptor >= 0:
            _run_cleanup_action(
                primary,
                label="closing append temporary artifact",
                action=lambda: os.close(temporary_descriptor),
            )
        if lock_descriptor >= 0:
            if lock_locked:
                _run_cleanup_action(
                    primary,
                    label="unlocking append serialization file",
                    action=lambda: fcntl.flock(
                        lock_descriptor,
                        fcntl.LOCK_UN,
                    ),
                )
            _run_cleanup_action(
                primary,
                label="closing append serialization file",
                action=lambda: os.close(lock_descriptor),
            )
        _finish_bound_parent(
            primary=primary,
            binding=binding,
            relative=relative,
            ancestry=ancestry,
            parent_descriptor=parent_descriptor,
        )
    return target


def unlink_run_file(
    run_dir: Path,
    path: str | Path,
    *,
    missing_ok: bool = False,
    expected_identity: PathIdentity | EntryIdentity | None = None,
) -> bool:
    """Unlink an exact run entry through the retained parent directory."""

    bound = _bound_run_file(run_dir, path)
    if bound is None:
        try:
            with _temporary_run_root_binding(Path(run_dir), create=False):
                return unlink_run_file(
                    run_dir,
                    path,
                    missing_ok=missing_ok,
                    expected_identity=expected_identity,
                )
        except FileNotFoundError:
            if missing_ok:
                return False
            raise
    binding, relative = bound
    try:
        parent_descriptor, name, ancestry = _open_bound_parent(
            binding,
            relative,
            create=False,
        )
    except FileNotFoundError:
        require_bound_run_root(Path(binding.lexical_root))
        if missing_ok:
            return False
        raise
    try:
        try:
            opened = os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            if missing_ok:
                return False
            raise
        opened_identity = _entry_identity(opened)
        if expected_identity is not None:
            expected_parts = tuple(expected_identity)
            if len(expected_parts) == 2:
                matches_expected = opened_identity[:2] == expected_parts
            elif len(expected_parts) == 3:
                matches_expected = opened_identity == expected_parts
            else:
                raise ValueError(
                    "expected unlink identity must be (st_dev, st_ino) "
                    "or (st_dev, st_ino, file_type)"
                )
            if not matches_expected:
                raise RunRootBindingError(
                    f"bound run unlink target no longer matches the "
                    f"caller's verified identity: {relative}"
                )
        current = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if _entry_identity(current) != opened_identity:
            raise RunRootBindingError(
                f"bound run unlink target identity changed: {relative}"
            )
        if not _remove_name_if_identity(
            parent_descriptor,
            name,
            expected_identity=opened_identity,
        ):
            raise RunRootBindingError(
                f"bound run unlink target changed during removal: {relative}"
            )
        os.fsync(parent_descriptor)
        return True
    finally:
        _finish_bound_parent(
            primary=sys.exception(),
            binding=binding,
            relative=relative,
            ancestry=ancestry,
            parent_descriptor=parent_descriptor,
        )


@contextmanager
def bind_run_root(
    run_dir: Path,
    *,
    expected_identity: PathIdentity,
    descriptor: int | None = None,
) -> Iterator[RunRootBinding]:
    """Propagate one pinned run inode through synchronous and async call trees."""

    lexical_root = _lexical_root(run_dir)
    existing = current_run_root_binding()
    if existing is not None:
        if (
            existing.lexical_root != lexical_root
            or existing.identity != expected_identity
        ):
            raise RunRootBindingError(
                "a different run root is already bound in this execution context"
            )
        require_bound_run_root(run_dir)
        if descriptor is not None:
            try:
                supplied = os.fstat(descriptor)
            except OSError as exc:
                raise RunRootBindingError(
                    f"bound run descriptor is unavailable: {run_dir}"
                ) from exc
            if (
                not stat.S_ISDIR(supplied.st_mode)
                or (supplied.st_dev, supplied.st_ino) != expected_identity
            ):
                raise RunRootBindingError(
                    f"bound run descriptor does not match {run_dir}"
                )
        try:
            yield existing
        finally:
            primary = sys.exception()
            _run_cleanup_actions(
                primary,
                [
                    (
                        "verifying nested bound run root",
                        lambda: require_bound_run_root(run_dir),
                    )
                ],
            )
        return

    owned_descriptor = descriptor is None
    bound_descriptor = -1
    token = None
    binding: RunRootBinding | None = None
    try:
        verify_run_root(run_dir, expected_identity=expected_identity)
        if descriptor is None:
            bound_descriptor = os.open(
                run_dir,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
            )
        else:
            bound_descriptor = descriptor
        opened = os.fstat(bound_descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != expected_identity
        ):
            raise RunRootBindingError(
                f"bound run descriptor does not match {run_dir}"
            )
        binding = RunRootBinding(
            lexical_root=lexical_root,
            identity=expected_identity,
            descriptor=bound_descriptor,
        )
        token = _ACTIVE_RUN_ROOT.set(binding)
        try:
            yield binding
        finally:
            primary = sys.exception()
            _run_cleanup_actions(
                primary,
                [
                    (
                        "verifying bound run root at context exit",
                        lambda: require_bound_run_root(run_dir),
                    )
                ],
            )
    finally:
        primary = sys.exception()
        cleanup_actions: list[tuple[str, Callable[[], object]]] = []
        if binding is not None:
            binding._lifetime.active = False
        if token is not None:
            cleanup_actions.append(
                (
                    "resetting bound run context",
                    lambda: _ACTIVE_RUN_ROOT.reset(token),
                )
            )
        if owned_descriptor and bound_descriptor >= 0:
            cleanup_actions.append(
                (
                    "closing owned bound run descriptor",
                    lambda: os.close(bound_descriptor),
                )
            )
        _run_cleanup_actions(primary, cleanup_actions)
