"""Frontend/CLI shared p860 boundary; existing media runtime owns generation leases."""
import asyncio
import copy
import subprocess
import uuid
from pathlib import Path
from typing import Any

try:
    from fastapi import HTTPException
except ModuleNotFoundError:  # The canonical CLI freezer also imports this boundary.
    class HTTPException(RuntimeError):
        pass
from pydantic import BaseModel, Field

from toc import sound_design as sound
from toc import sound_authoring as authoring


def app():
    from server import image_gen_app
    return image_gen_app


class SoundRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    video_set_hash: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=0)


class SoundCueRequest(SoundRequest):
    item_id: str = Field(min_length=1, max_length=100)
    settings: sound.CueSettings
    metadata: authoring.CueMetadata | None = None


class SoundCueCreateRequest(SoundRequest):
    cue: authoring.CueDraft


class SoundCueDeleteRequest(SoundRequest):
    item_id: str = Field(min_length=1, max_length=100)


class SoundAuthorRequest(SoundRequest):
    instructions: str = Field(default="", max_length=6000)


_designing_runs: set[str] = set()


class NativeAudioRequest(SoundRequest):
    item_id: str = Field(min_length=1, max_length=100)
    settings: sound.NativeAudioSettings


class SoundGenerateRequest(SoundRequest):
    item_id: str = Field(min_length=1, max_length=100)


class SoundCompleteRequest(SoundRequest):
    without_sound: bool = False


class SoundMixRequest(SoundRequest):
    settings: sound.MixSettings


_preview_slots = asyncio.Semaphore(1)


def video_context(root: Path, data: dict[str, Any] | None = None) -> dict[str, Any]:
    api = app()
    if data is None:
        _, _, data = api._read_manifest_data(root)
    videos = []
    elapsed = 0.0
    for target in api._manifest_video_targets(data):
        node = target["cut"]
        generation = api._dict_value(node.get("video_generation"))
        render = api._dict_value(node.get("render"))
        selector = str(target["selector"])
        candidate = api._candidate_video_output_for_item(root, selector, manifest_data=data)
        path = str(candidate or generation.get("output") or render.get("video_path") or "")
        api._validate_run_relative_video_path(root, path, must_exist=True)
        api._assert_current_video_candidate_path(root, selector, path)
        source = sound.safe_path(root, path)
        measured = api._probe_media_duration_seconds(source)
        duration = float((None if target.get("is_render_unit") else render.get("video_duration_seconds")) or generation.get("duration_seconds") or 0)
        if measured is None or duration <= 0 or measured + 0.35 < duration:
            raise ValueError(f"{selector}: 生成動画の尺が未確定か不足しています")
        scene = target["scene"]
        native_audio = generation.get("native_audio")
        native_audio = native_audio if isinstance(native_audio, dict) else {}
        mode = str(native_audio.get("mode") or "off")
        if mode not in {"off", "natural_sound", "dialogue_and_sound"}:
            raise ValueError(f"{selector}: native_audio.mode が不正です")
        audio_stream = None
        if mode != "off":
            audio_stream = sound.probe_audio_stream(source)
            if audio_stream is None:
                raise ValueError(f"{selector}: ネイティブ音声が要求されていますが、動画に音声ストリームがありません")
            try:
                subprocess_result = subprocess.run(
                    ["ffmpeg", "-v", "error", "-i", str(source), "-map", f"0:{audio_stream['index']}", "-f", "null", "-"],
                    check=False, capture_output=True, timeout=180)
            except subprocess.TimeoutExpired as exc:
                raise ValueError(f"{selector}: ネイティブ音声のデコード確認がタイムアウトしました") from exc
            if subprocess_result.returncode:
                raise ValueError(f"{selector}: ネイティブ音声ストリームをデコードできません")
        candidate_revision = None
        resolver = getattr(api, "_current_video_candidate_provenance", None)
        if resolver:
            provenance = resolver(root, selector, manifest_data=data)
            candidate_revision = provenance.get("revision_id") if provenance else None
        context = str(generation.get("prompt") or node.get("description") or scene.get("description") or scene.get("title") or "画面内の動きと環境")
        video = {"item_id": selector, "path": path, "sha256": sound.file_hash(source),
                 "start_seconds": elapsed, "duration_seconds": duration, "context": context,
                 "source": {k: generation.get(k) for k in ("prompt", "tool", "api_prompt", "compiled_prompt") if k in generation}}
        if mode != "off":
            video.update(native_audio_mode=mode, audio_stream=audio_stream,
                         candidate_revision=candidate_revision)
        videos.append(video)
        elapsed += duration
    if not videos:
        raise ValueError("動画生成の完了後にBGM・SEへ進めます")
    hash_data = copy.deepcopy(data)
    narration_files = []
    for target in api._manifest_scene_targets(hash_data):
        narration = api._dict_value(api._dict_value(target["cut"].get("audio")).get("narration"))
        if api._narration_has_intentional_silence(narration):
            # p910 may materialize silence; that synthetic file is not an input revision.
            narration["output"] = ""
            continue
        path = str(narration.get("output") or "")
        if path:
            narration_files.append({"selector": target["selector"], "path": path, "sha256": sound.file_hash(sound.safe_path(root, path))})
    fingerprint = {"videos": videos, "narration_files": narration_files, "audio_set_hash": api._manifest_narration_audio_set_hash(hash_data),
                   "timeline_hash": api._manifest_narration_timeline_hash(data)}
    return {"video_set_hash": sound.digest(fingerprint), "duration_seconds": elapsed, "videos": videos}


def read_status(root: Path) -> dict[str, Any]:
    plan = sound.load(root)
    context: dict[str, Any] = {"videos": [], "video_set_hash": "", "duration_seconds": 0}
    error = ""
    approved = False
    ready = False
    try:
        context = video_context(root)
        sound.require_current(plan, context)
        approved = True
        if plan.get("status") == "completed":
            sound.render_plan(root, plan, context)
            ready = True
    except (ValueError, FileNotFoundError) as exc:
        error = str(exc)
    for cue in plan.get("cues", []):
        cue["current_request_hash"] = sound.request_hash(cue)
    return {"runId": root.name, "process": "p860", "plan": plan or None,
            "context": context, "approved": approved, "ready": ready, "blockedReason": error}


def require_request(root: Path, req: SoundRequest) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = sound.load(root)
    context = video_context(root)
    if context["video_set_hash"] != req.video_set_hash:
        raise ValueError("動画・尺が変更されました。再読込して承認してください")
    if plan.get("revision", 0) != req.revision:
        raise ValueError("BGM・SEの設定が更新されています。再読込してください")
    sound.require_current(plan, context)
    return plan, context


def persist(root: Path, plan: dict[str, Any]) -> None:
    sound.save(root, plan)
    completed = plan["status"] == "completed"
    app().append_state_snapshot(root / "state.txt", {
        "status": "P860", "runtime.stage": "sound_design",
        "slot.p840.status": "done", "slot.p860.status": "done" if completed else "in_progress",
        "slot.p860.requirement": "required", "stage.sound_design.status": "completed" if completed else "in_progress",
        "artifact.sound_design": str((root / sound.ARTIFACT).resolve()),
        "human_choice.video.video_set_hash": plan["video_approval"]["video_set_hash"],
        "human_choice.video.actor": plan["video_approval"]["actor"],
        "human_choice.video.at": plan["video_approval"]["at"],
        "slot.p910.status": "pending", "slot.p920.status": "pending",
        "stage.render.status": "pending",
    })


async def status(run_id: str) -> dict[str, Any]:
    root = app().safe_run_dir(run_id, app().ROOT)
    try:
        return await asyncio.to_thread(read_status, root)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc)) from exc


async def approve_video(req: SoundRequest) -> dict[str, Any]:
    api = app()
    root = api.safe_run_dir(req.run_id, api.ROOT)
    try:
        async with api._serialized_run_write(root, "run_artifacts"):
            context = await asyncio.to_thread(video_context, root)
            previous = sound.load(root)
            if context["video_set_hash"] != req.video_set_hash or previous.get("revision", 0) != req.revision:
                raise ValueError("動画または設定が更新されました。再読込して承認してください")
            if previous.get("video_approval", {}).get("video_set_hash") == req.video_set_hash:
                return read_status(root)
            if previous:
                sound.write_json(root, f"logs/sound_design/previous_{uuid.uuid4().hex}.json", previous)
            plan = sound.approve(context, actor="frontend")
            plan["revision"] = previous.get("revision", 0)
            persist(root, plan)
        return await asyncio.to_thread(read_status, root)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(409, str(exc)) from exc


async def save_cue(req: SoundCueRequest) -> dict[str, Any]:
    api = app()
    root = api.safe_run_dir(req.run_id, api.ROOT)
    try:
        async with api._serialized_run_write(root, "run_artifacts"):
            plan, _ = await asyncio.to_thread(require_request, root, req)
            previous = copy.deepcopy(plan)
            sound.update_cue(root, plan, req.item_id, req.settings)
            if req.metadata is not None:
                authoring.validate_source(req.metadata.source_selector, plan['video_approval'])
                cue = sound.get_cue(plan, req.item_id)
                metadata = req.metadata.model_dump()
                if any(cue.get(k) != v for k, v in metadata.items()):
                    cue.update(metadata)
                    plan['status'] = 'draft'
            if plan != previous:
                persist(root, plan)
        return await asyncio.to_thread(read_status, root)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(409, str(exc)) from exc


async def create_cue(req: SoundCueCreateRequest) -> dict[str, Any]:
    api = app()
    root = api.safe_run_dir(req.run_id, api.ROOT)
    try:
        async with api._serialized_run_write(root, 'run_artifacts'):
            plan, context = await asyncio.to_thread(require_request, root, req)
            authoring.add_cue(plan, context, req.cue)
            persist(root, plan)
        return await asyncio.to_thread(read_status, root)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(409, str(exc)) from exc


async def delete_cue(req: SoundCueDeleteRequest) -> dict[str, Any]:
    api = app()
    root = api.safe_run_dir(req.run_id, api.ROOT)
    try:
        async with api._serialized_run_write(root, 'run_artifacts'):
            plan, _ = await asyncio.to_thread(require_request, root, req)
            authoring.archive_cue(plan, req.item_id)
            persist(root, plan)
        return await asyncio.to_thread(read_status, root)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(409, str(exc)) from exc


async def author_design(req: SoundAuthorRequest) -> dict[str, Any]:
    api = app()
    root = api.safe_run_dir(req.run_id, api.ROOT)
    key = str(root.resolve())
    if key in _designing_runs:
        raise HTTPException(409, 'この作品の音響設計は実行中です')
    _designing_runs.add(key)
    design_id = uuid.uuid4().hex
    log_prefix = f'logs/sound_design/design_{design_id}'
    try:
        async with api._serialized_run_write(root, 'run_artifacts'):
            plan, context = await asyncio.to_thread(require_request, root, req)
            snapshot, hashes = await asyncio.to_thread(authoring.source_snapshot, root, api.ROOT)
            plan_hash = sound.digest(plan)
            prompt = authoring.build_prompt(snapshot, context, plan, req.instructions)
            sound.write_json(root, log_prefix + '.request.json', {'policy': authoring.POLICY,
                'source_hashes': hashes, 'revision': req.revision, 'video_set_hash': req.video_set_hash,
                'plan_hash': plan_hash, 'prompt': prompt, 'status': 'running'})
        payload, provenance = await authoring.author(prompt, root)
        sound.write_json(root, log_prefix + '.result.json', {'status': 'received', 'payload': payload, 'provenance': provenance})
        proposal = authoring.SoundDesignDraft.model_validate(payload)
        async with api._serialized_run_write(root, 'run_artifacts'):
            current, current_context = await asyncio.to_thread(require_request, root, req)
            _, current_hashes = await asyncio.to_thread(authoring.source_snapshot, root, api.ROOT)
            if hashes != current_hashes or plan_hash != sound.digest(current):
                raise ValueError('音響設計中に原稿・設定・設計書が変更されました。再設計してください')
            authoring.apply_design(current, current_context, proposal, design_id=design_id)
            current['designs'][-1].update(source_hashes=hashes, provenance=provenance, result_log=log_prefix + '.result.json')
            persist(root, current)
            sound.write_json(root, log_prefix + '.status.json', {'status': 'applied', 'cue_count': len(proposal.cues)})
        return await asyncio.to_thread(read_status, root)
    except (ValueError, FileNotFoundError) as exc:
        sound.write_json(root, log_prefix + '.status.json', {'status': 'rejected', 'reason': str(exc)[:2000]})
        raise HTTPException(409, str(exc)) from exc
    except asyncio.CancelledError:
        sound.write_json(root, log_prefix + '.status.json', {'status': 'interrupted'})
        raise
    except Exception as exc:
        sound.write_json(root, log_prefix + '.status.json', {'status': 'failed', 'error_type': type(exc).__name__})
        raise HTTPException(502, 'LLM音響設計に失敗しました。既存の音源・設定は保持されています。') from exc
    finally:
        _designing_runs.discard(key)


async def save_native_audio(req: NativeAudioRequest) -> dict[str, Any]:
    api = app()
    root = api.safe_run_dir(req.run_id, api.ROOT)
    try:
        async with api._serialized_run_write(root, "run_artifacts"):
            plan, _ = await asyncio.to_thread(require_request, root, req)
            previous = copy.deepcopy(plan)
            sound.update_native_track(plan, req.item_id, req.settings)
            if plan != previous:
                persist(root, plan)
        return await asyncio.to_thread(read_status, root)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(409, str(exc)) from exc


async def save_mix(req: SoundMixRequest) -> dict[str, Any]:
    api = app()
    root = api.safe_run_dir(req.run_id, api.ROOT)
    try:
        async with api._serialized_run_write(root, 'run_artifacts'):
            plan, context = await asyncio.to_thread(require_request, root, req)
            settings = req.settings.model_dump()
            if sound.MixSettings.model_validate(plan.get('mix', {})).model_dump() != settings:
                plan['mix'] = settings
                # Explicit saving commits gain changes, without discarding selected cues.
                if plan['status'] == 'completed':
                    sound.render_plan(root, plan, context)
                persist(root, plan)
        return await asyncio.to_thread(read_status, root)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(409, str(exc)) from exc


def build_mix_preview(root: Path, plan: dict[str, Any], context: dict[str, Any],
                      data: dict[str, Any], directory: Path) -> Path:
    """Prepare an isolated audition, using the final export mixer without p910 writes."""
    api = app()
    snapshot = sound.render_plan(root, plan, context)
    if api._revision_aware_narration_items(data):
        api._require_narration_ready_for_video(root)
    directory.mkdir(parents=True, exist_ok=False)
    audio_paths = []
    for index, target in enumerate(api._manifest_scene_targets(data)):
        node = target['cut']
        narration = api._dict_value(api._dict_value(node.get('audio')).get('narration'))
        render = api._dict_value(node.get('render'))
        duration = float(render.get('video_duration_seconds') or node.get('video_generation', {}).get('duration_seconds') or 0)
        offset = float(render.get('narration_offset_seconds') or 0)
        if duration <= 0 or not 0 <= offset <= duration:
            raise ValueError('ナレーションの尺・開始位置を確認してください')
        dest = directory / f'narration_{index}.wav'
        command = ['ffmpeg', '-v', 'error', '-y']
        if api._narration_has_intentional_silence(narration):
            command += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
        else:
            source = sound.safe_path(root, str(narration.get('output') or ''))
            actual = sound.probe_audio(source)
            if actual + offset > duration + 0.05:
                raise ValueError(f"{target['selector']}: 音声が映像尺を超えています")
            command += ['-i', str(source)]
        command += ['-af', f'adelay={round(offset * 1000)}:all=1,apad,atrim=duration={duration}',
                    '-t', str(duration), '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', str(dest)]
        subprocess.run(command, check=True, capture_output=True, timeout=300)
        audio_paths.append(dest)
    listing = directory / 'narration.txt'
    listing.write_text('\n'.join(api._concat_list_line(path) for path in audio_paths) + '\n')
    mixed = directory / 'mix.m4a'
    sound.mix_audio(snapshot, listing, mixed)
    clips = []
    for index, video in enumerate(context['videos']):
        source = sound.safe_path(root, video['path'])
        if sound.file_hash(source) != video['sha256']:
            raise ValueError('試聴の準備中に動画が変更されました')
        dest = directory / f'video_{index}.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(source), '-an',
                        '-vf', 'fps=24,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1',
                        '-t', str(video['duration_seconds']), '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '26',
                        '-pix_fmt', 'yuv420p', '-video_track_timescale', '12288', str(dest)],
                       check=True, capture_output=True, timeout=600)
        api._require_prepared_media_duration(dest, expected_seconds=video['duration_seconds'], label=video['item_id'])
        clips.append(dest)
    clip_list = directory / 'clips.txt'
    clip_list.write_text('\n'.join(api._concat_list_line(path) for path in clips) + '\n')
    output = directory / 'preview.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(clip_list),
                    '-i', str(mixed), '-map', '0:v:0', '-map', '1:a:0', '-c', 'copy',
                    '-t', str(context['duration_seconds']), '-movflags', '+faststart', str(output)],
                   check=True, capture_output=True, timeout=300)
    from toc.providers.video_validation import verify_generated_video
    verify_generated_video(output, duration_seconds=context['duration_seconds'], aspect_ratio='16:9', require_audio=True)
    sound.write_json(root, (directory / 'sound_snapshot.json').relative_to(root).as_posix(), snapshot)
    # These intermediates belong exclusively to this UUID audition, not source media.
    for temporary in directory.iterdir():
        intermediate = (temporary.name.startswith(('narration_', 'video_', 'mix_narration_master.'))
                        or temporary.name in {'clips.txt', 'narration.txt', 'mix.m4a'})
        if temporary.is_file() and intermediate:
            temporary.unlink()
    return output


async def mix_preview(req: SoundMixRequest) -> dict[str, Any]:
    api = app()
    root = api.safe_run_dir(req.run_id, api.ROOT)
    try:
        async with _preview_slots:
            async with api._serialized_run_write(root, 'run_artifacts'):
                plan, context = await asyncio.to_thread(require_request, root, req)
                original_hash = sound.digest(plan)
                data = api._read_manifest_data(root)[2]
                draft = copy.deepcopy(plan)
                draft['mix'] = req.settings.model_dump()
                sound.render_plan(root, draft, context)
                directory = sound.safe_path(root, f'assets/test/mix_preview/{uuid.uuid4().hex}')
            output = await asyncio.to_thread(build_mix_preview, root, draft, context, data, directory)
            async with api._serialized_run_write(root, 'run_artifacts'):
                current, _ = await asyncio.to_thread(require_request, root, req)
                if sound.digest(current) != original_hash:
                    raise ValueError('試聴中に音声設定が変更されました。再読込してください')
            return {'runId': req.run_id, 'path': output.relative_to(root).as_posix(),
                    'settings': req.settings.model_dump(), 'revision': req.revision,
                    'video_set_hash': req.video_set_hash}
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(409, str(exc)) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise HTTPException(500, '試聴用動画の作成に失敗しました。音声素材とFFmpegを確認してください') from exc


async def generate(req: SoundGenerateRequest) -> dict[str, Any]:
    api = app()
    root = api.safe_run_dir(req.run_id, api.ROOT)
    api.load_env_files(repo_root=api.ROOT)
    try:
        async with api._serialized_run_write(root, "run_artifacts"):
            plan, context = await asyncio.to_thread(require_request, root, req)
            cue = sound.get_cue(plan, req.item_id)
            provider = sound.provider_request(cue)
            candidate_id = uuid.uuid4().hex
            request = {"id": candidate_id, "cue_id": cue["id"], "provider": "elevenlabs", "request": provider,
                       "request_hash": sound.request_hash(cue), "video_set_hash": context["video_set_hash"],
                       "created_at": sound.now(), "path": f"assets/sound/{cue['id']}/{candidate_id}.mp3"}
            from toc.media_resume import ACTIVE_MEDIA_JOURNAL
            journal = ACTIVE_MEDIA_JOURNAL.get()
            if journal is not None:
                for video in context["videos"]:
                    journal.bind_file(video["path"])
            sound.write_json(root, f"logs/sound_design/{candidate_id}.request.json", request)
        candidate = {**request, "status": "failed"}
        try:
            audio = await asyncio.to_thread(sound.generate_audio, provider)
            path = sound.safe_path(root, request["path"])
            from scripts.world_walk_source import ensure_directory_relative_nofollow, write_regular_file_nofollow
            binding = api._assert_bound_run_root(root)
            identity = binding.identity if binding else None
            ensure_directory_relative_nofollow(root, str(Path(request["path"]).parent), expected_root_identity=identity)
            write_regular_file_nofollow(destination_root=root, destination_relative=request["path"],
                                        expected_destination_root_identity=identity, data=audio)
            candidate.update(duration_seconds=await asyncio.to_thread(sound.probe_audio, path),
                             sha256=sound.file_hash(path), status="completed")
        except Exception as exc:
            candidate.update(status="failed", path=None, error=str(exc)[:2000])
        async with api._serialized_run_write(root, "run_artifacts"):
            current = sound.load(root)
            try:
                current_context = await asyncio.to_thread(video_context, root)
            except (ValueError, FileNotFoundError):
                current_context = {}
            if current_context.get("video_set_hash") != request["video_set_hash"] or current.get("video_approval", {}).get("video_set_hash") != request["video_set_hash"]:
                candidate.update(status="stale", error="生成中に動画・尺が変更されました。再承認してください")
            else:
                current_cue = next((c for c in current.get('cues', []) if c['id'] == req.item_id), None)
                if current_cue is None:
                    candidate.update(status='stale', error='生成中に音の項目が削除されました')
                    archived = next((c for c in current.get('archived_cues', []) if c['id'] == req.item_id), None)
                    if archived is not None:
                        archived.setdefault('candidates', []).append(candidate)
                else:
                    if sound.request_hash(current_cue) != request["request_hash"]:
                        candidate.update(status="stale", error="生成中に生成指示が変更されました")
                    current_cue["candidates"].append(candidate)
                sound.write_json(root, sound.ARTIFACT, current)
            sound.write_json(root, f"logs/sound_design/{candidate_id}.result.json", candidate)
        return {"runId": req.run_id, "status": candidate["status"], "candidates": [candidate]}
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(409, str(exc)) from exc


async def complete(req: SoundCompleteRequest) -> dict[str, Any]:
    api = app()
    root = api.safe_run_dir(req.run_id, api.ROOT)
    try:
        async with api._serialized_run_write(root, "run_artifacts"):
            plan, context = await asyncio.to_thread(require_request, root, req)
            if req.without_sound:
                for cue in plan["cues"]:
                    cue["enabled"] = False
                for track in plan.get("native_tracks", []):
                    track["enabled"] = False
            elif not any(c["enabled"] for c in plan["cues"]) and not any(t["enabled"] for t in plan.get("native_tracks", [])):
                raise ValueError("候補を採用するか「BGM・SEなしで確定」を選んでください")
            plan["status"] = "completed"
            sound.render_plan(root, plan, context)
            plan["completion"] = {"actor": "frontend", "at": sound.now(), "without_sound": req.without_sound}
            persist(root, plan)
        return await asyncio.to_thread(read_status, root)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(409, str(exc)) from exc


def freeze(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    return sound.render_plan(root, sound.load(root), video_context(root, data))


def install(api) -> None:
    if not hasattr(api.router, "add_api_route"):
        return
    global durable_generate
    durable_generate = api._durable_media_operation("sound")(generate)
    prefix = "/api/image-gen/sound-design"
    api.router.add_api_route(prefix, status, methods=["GET"])
    api.router.add_api_route(prefix + "/approve-video", approve_video, methods=["POST"])
    api.router.add_api_route(prefix + "/cue", save_cue, methods=["POST"])
    api.router.add_api_route(prefix + "/cue-create", create_cue, methods=["POST"])
    api.router.add_api_route(prefix + "/cue-delete", delete_cue, methods=["POST"])
    api.router.add_api_route(prefix + "/design", author_design, methods=["POST"])
    api.router.add_api_route(prefix + "/native-audio", save_native_audio, methods=["POST"])
    api.router.add_api_route(prefix + "/mix", save_mix, methods=["POST"])
    api.router.add_api_route(prefix + "/mix-preview", mix_preview, methods=["POST"])
    api.router.add_api_route(prefix + "/generate", durable_generate, methods=["POST"])
    api.router.add_api_route(prefix + "/complete", complete, methods=["POST"])
