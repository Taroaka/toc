"""Explicit content diagnostics; transport/environment exceptions stay separate."""
from __future__ import annotations


class AuthoringValidationError(ValueError, RuntimeError):
    def __init__(self, message: str, *, owner_stage: str = 'p420', target: str = ''):
        super().__init__(message)
        self.owner_stage = owner_stage
        self.target = target


class MediaOutputError(RuntimeError):
    """A provider returned no usable image; unsafe inputs remain runtime failures."""
    def __init__(self, message, *, kind=None, item_ids=()):
        super().__init__(message)
        self.kind = kind
        self.item_ids = tuple(item_ids)


def diagnostic_subprocess_run(command, **kwargs):
    """Decode only the dedicated exit/status emitted by our materializers."""
    import json
    import subprocess
    try:
        return subprocess.run(command, **kwargs)
    except subprocess.CalledProcessError as exc:
        if exc.returncode != 38:
            raise
        try:
            data = json.loads(exc.stderr.strip().splitlines()[-1])
            if data.get('schema') != 'toc.authoring_error.v1' or data.get('owner_stage') not in {'p220', 'p330', 'p420'} or not isinstance(data.get('message'), str):
                raise ValueError('invalid diagnostic')
        except (ValueError, AttributeError, IndexError):
            raise exc
        raise AuthoringValidationError(data['message'], owner_stage=data['owner_stage']) from exc


def diagnostic_cli(main):
    import json
    import sys
    try:
        main()
    except AuthoringValidationError as exc:
        print(json.dumps({'schema': 'toc.authoring_error.v1', 'owner_stage': exc.owner_stage,
            'message': str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(38) from exc
