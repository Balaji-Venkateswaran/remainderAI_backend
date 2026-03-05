import asyncio
import os
import tempfile
from functools import lru_cache

from dotenv import load_dotenv
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from livekit import api

load_dotenv()

router = APIRouter(prefix="/voice", tags=["Voice"])

LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "auto")
WHISPER_COMPUTE = os.environ.get("WHISPER_COMPUTE", "int8")
WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "en")


def create_token(room: str, identity: str, name: str | None) -> str:
    token = (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name(name or identity)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .to_jwt()
    )
    return token


@router.get("/token")
def token(
    room: str = Query("demo"),
    identity: str = Query("web-user"),
    name: str | None = Query(None),
):
    return {"token": create_token(room, identity, name)}


@lru_cache(maxsize=1)
def _load_whisper_model():
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("faster-whisper is not installed") from exc

    return WhisperModel(
        WHISPER_MODEL,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE,
    )


def _transcribe_bytes(wav_bytes: bytes, language: str | None) -> tuple[str, str | None]:
    model = _load_whisper_model()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(wav_bytes)
        tmp.flush()
        wav_path = tmp.name

    try:
        segments, info = model.transcribe(wav_path, language=language)
        text = "".join(segment.text for segment in segments).strip()
        detected_language = getattr(info, "language", None)
        return text, detected_language
    finally:
        try:
            os.remove(wav_path)
        except OSError:
            pass


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str | None = Query(None),
):
    wav_bytes = await file.read()
    if not wav_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    try:
        text, detected_language = await asyncio.to_thread(
            _transcribe_bytes,
            wav_bytes,
            language or WHISPER_LANGUAGE,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "text": text,
        "language": detected_language,
    }
