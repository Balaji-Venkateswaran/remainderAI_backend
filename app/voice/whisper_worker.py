import asyncio
import os
import tempfile
import uuid

from dotenv import load_dotenv
from faster_whisper import WhisperModel
from livekit import api, rtc

load_dotenv()

LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "ws://127.0.0.1:7880")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")
LIVEKIT_ROOM = os.environ.get("LIVEKIT_ROOM", "demo")

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "auto")
WHISPER_COMPUTE = os.environ.get("WHISPER_COMPUTE", "int8")
WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "en")

CHUNK_SECONDS = float(os.environ.get("CHUNK_SECONDS", "1.0"))


def build_token(identity: str) -> str:
    return (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=LIVEKIT_ROOM,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .to_jwt()
    )


def transcribe_bytes(model: WhisperModel, wav_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(wav_bytes)
        tmp.flush()
        wav_path = tmp.name

    try:
        segments, _info = model.transcribe(wav_path)
        return "".join(segment.text for segment in segments).strip()
    finally:
        try:
            os.remove(wav_path)
        except OSError:
            pass


async def publish_segment(
    room: rtc.Room,
    participant_identity: str,
    track_sid: str,
    text: str,
    start_time_ms: int,
    end_time_ms: int,
) -> None:
    if not text:
        return

    segment = rtc.TranscriptionSegment(
        id=str(uuid.uuid4()),
        text=text,
        start_time=start_time_ms,
        end_time=end_time_ms,
        language=WHISPER_LANGUAGE,
        final=True,
    )

    transcription = rtc.Transcription(
        participant_identity=participant_identity,
        track_sid=track_sid,
        segments=[segment],
    )

    await room.local_participant.publish_transcription(transcription)
    await room.local_participant.publish_data(
        text.encode("utf-8"), reliable=True, topic="transcript"
    )


async def handle_audio_track(
    room: rtc.Room,
    participant_identity: str,
    track: rtc.Track,
    publication: rtc.RemoteTrackPublication,
    model: WhisperModel,
) -> None:
    if track.kind != rtc.TrackKind.KIND_AUDIO:
        return

    print(
        f"[worker] Subscribed to audio track: {publication.sid} from {participant_identity}"
    )
    stream = rtc.AudioStream(track)

    buffer: list[rtc.AudioFrame] = []
    buffered_ms = 0
    chunk_ms = int(CHUNK_SECONDS * 1000)
    timeline_ms = 0

    async for event in stream:
        frame = event.frame if hasattr(event, "frame") else event
        buffer.append(frame)
        frame_ms = int(frame.samples_per_channel / frame.sample_rate * 1000)
        buffered_ms += frame_ms

        if buffered_ms >= chunk_ms:
            combined = rtc.combine_audio_frames(buffer)
            wav_bytes = combined.to_wav_bytes()
            text = await asyncio.to_thread(transcribe_bytes, model, wav_bytes)
            print(f"[worker] Transcribed chunk ({buffered_ms}ms): {text!r}")

            await publish_segment(
                room,
                participant_identity,
                publication.sid,
                text,
                timeline_ms,
                timeline_ms + buffered_ms,
            )

            timeline_ms += buffered_ms
            buffer = []
            buffered_ms = 0


async def main() -> None:
    model = WhisperModel(
        WHISPER_MODEL,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE,
    )

    room = rtc.Room()

    def on_track_subscribed(
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        print(
            f"[worker] Track subscribed: kind={track.kind} sid={publication.sid} participant={participant.identity}"
        )
        asyncio.create_task(
            handle_audio_track(
                room,
                participant.identity,
                track,
                publication,
                model,
            )
        )

    room.on("track_subscribed", on_track_subscribed)

    token = build_token("whisper-worker")
    print(f"[worker] Connecting to {LIVEKIT_URL} room={LIVEKIT_ROOM}")
    await room.connect(LIVEKIT_URL, token)
    print("[worker] Connected and waiting for tracks...")

    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
