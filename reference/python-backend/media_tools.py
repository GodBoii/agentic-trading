import base64
import binascii
import logging
import os
import time
import traceback
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

from agno.agent import Agent
from agno.media import Image, Video
from agno.models.openrouter import OpenRouter
from agno.run.agent import RunOutput
from agno.tools import Toolkit

from sandbox_persistence import get_persistence_service
from supabase_client import supabase_client

logger = logging.getLogger(__name__)

OPENROUTER_VIDEO_URL = "https://openrouter.ai/api/v1/videos"
IMAGE_MODEL_ID = "sourceful/riverflow-v2-fast"
VIDEO_MODEL_ID = "google/veo-3.1-lite"


class MediaTools(Toolkit):
    """Generate images and videos, persist them, and notify the frontend by URL."""

    def __init__(self, custom_tool_config: Dict[str, Any]):
        super().__init__(
            name="media_tools",
            tools=[self.generate_image, self.generate_video],
        )

        self.socketio = custom_tool_config.get("socketio")
        self.sid = custom_tool_config.get("sid")
        self.message_id = custom_tool_config.get("message_id")
        self.conversation_id = custom_tool_config.get("conversation_id")
        self.user_id = custom_tool_config.get("user_id")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

        if not self.openrouter_api_key:
            logger.error("MediaTools: OPENROUTER_API_KEY is not configured")

    def generate_image(
        self,
        prompt: str,
        images: Optional[Sequence[Image]] = None,
        videos: Optional[Sequence[Video]] = None,
        session_state: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate an image from a prompt and optional attached reference media."""
        if not self.openrouter_api_key:
            return "Image generation is unavailable because OPENROUTER_API_KEY is not configured."

        try:
            reference_image_urls, reference_video_urls = self._collect_attachment_urls(
                session_state=session_state,
                images=images,
                videos=videos,
            )
            prompt_for_generation = self._build_prompt_with_reference_urls(
                prompt=prompt,
                image_urls=[],
                video_urls=reference_video_urls,
            )

            # Use an internal Agno agent so we receive the generated image back as
            # RunOutput media, then persist it ourselves for the frontend.
            artist_agent = Agent(
                name="media_image_generator",
                model=OpenRouter(
                    id=IMAGE_MODEL_ID,
                    modalities=["image"],
                ),
                send_media_to_model=True,
                store_media=True,
                debug_mode=False,
            )

            run_output: RunOutput = artist_agent.run(
                prompt_for_generation,
                images=list(images) if images else None,
            )

            image_bytes, mime_type = self._extract_generated_image(run_output)
            artifact_id, signed_url, file_name = self._persist_generated_media(
                media_bytes=image_bytes,
                mime_type=mime_type,
                media_kind="image",
                prompt=prompt,
                source_urls=reference_image_urls + reference_video_urls,
                provider_response={
                    "content": getattr(run_output, "content", None),
                    "model": IMAGE_MODEL_ID,
                },
            )

            provider_text = str(getattr(run_output, "content", "") or "").strip()
            summary_text = provider_text or "Image generated. The user can view it in the frontend."
            self._emit_media_generated(
                artifact_id=artifact_id,
                media_type="image",
                media_url=signed_url,
                mime_type=mime_type,
                file_name=file_name,
            )
            return f"{summary_text}\n\n```image\n{artifact_id}\n```"
        except Exception as exc:
            logger.error("MediaTools.generate_image failed: %s\n%s", exc, traceback.format_exc())
            return f"Image generation failed: {exc}"

    def generate_video(
        self,
        prompt: str,
        images: Optional[Sequence[Image]] = None,
        videos: Optional[Sequence[Video]] = None,
        session_state: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate a video from a prompt and optional attached reference media."""
        if not self.openrouter_api_key:
            return "Video generation is unavailable because OPENROUTER_API_KEY is not configured."

        try:
            image_urls, video_urls = self._collect_attachment_urls(
                session_state=session_state,
                images=images,
                videos=videos,
            )
            payload: Dict[str, Any] = {
                "model": VIDEO_MODEL_ID,
                "prompt": self._build_prompt_with_reference_urls(
                    prompt=prompt,
                    image_urls=[],
                    video_urls=video_urls,
                ),
                "duration": 4,
                "resolution": "720p",
                "aspect_ratio": "16:9",
            }

            if image_urls:
                payload["input_references"] = [
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url},
                    }
                    for image_url in image_urls[:4]
                ]

            submit_response = requests.post(
                OPENROUTER_VIDEO_URL,
                headers=self._openrouter_headers(),
                json=payload,
                timeout=90,
            )
            submit_response.raise_for_status()
            job = submit_response.json()

            polling_url = str(job.get("polling_url") or "").strip()
            if polling_url.startswith("/"):
                polling_url = f"https://openrouter.ai{polling_url}"
            if not polling_url:
                raise RuntimeError("OpenRouter did not return a polling URL for the video job.")

            status_payload = self._poll_video_job(polling_url)
            unsigned_urls = status_payload.get("unsigned_urls") or []
            if not unsigned_urls:
                raise RuntimeError("Video generation completed without any downloadable video URLs.")

            video_response = requests.get(unsigned_urls[0], timeout=300)
            video_response.raise_for_status()
            video_bytes = video_response.content

            artifact_id, signed_url, file_name = self._persist_generated_media(
                media_bytes=video_bytes,
                mime_type="video/mp4",
                media_kind="video",
                prompt=prompt,
                source_urls=image_urls + video_urls,
                provider_response=status_payload,
            )

            self._emit_media_generated(
                artifact_id=artifact_id,
                media_type="video",
                media_url=signed_url,
                mime_type="video/mp4",
                file_name=file_name,
            )
            return f"Video generated. The user can view it in the frontend.\n\n```video\n{artifact_id}\n```"
        except Exception as exc:
            logger.error("MediaTools.generate_video failed: %s\n%s", exc, traceback.format_exc())
            return f"Video generation failed: {exc}"

    def _openrouter_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
        }

    def _build_prompt_with_reference_urls(self, prompt: str, image_urls: List[str], video_urls: List[str]) -> str:
        lines = [prompt.strip()]
        if image_urls:
            lines.append("")
            lines.append("Reference image URLs:")
            lines.extend(f"- {url}" for url in image_urls)
        if video_urls:
            lines.append("")
            lines.append("Reference video URLs:")
            lines.extend(f"- {url}" for url in video_urls)
        return "\n".join(line for line in lines if line is not None).strip()

    def _collect_attachment_urls(
        self,
        *,
        session_state: Optional[Dict[str, Any]],
        images: Optional[Sequence[Image]] = None,
        videos: Optional[Sequence[Video]] = None,
    ) -> Tuple[List[str], List[str]]:
        turn_context = (session_state or {}).get("turn_context") or {}
        files = turn_context.get("files") or []
        image_urls: List[str] = []
        video_urls: List[str] = []

        for file_info in files:
            if not isinstance(file_info, dict):
                continue
            storage_path = str(file_info.get("path") or "").strip()
            mime_type = str(file_info.get("type") or "").strip().lower()
            if not storage_path:
                continue
            signed_url = self._create_signed_media_url(storage_path, expires_in=7200)
            if not signed_url:
                continue
            if mime_type.startswith("image/"):
                image_urls.append(signed_url)
            elif mime_type.startswith("video/"):
                video_urls.append(signed_url)

        if not image_urls and images:
            image_urls = [url for url in (self._image_to_data_url(image) for image in images[:4]) if url]
        if not video_urls and videos:
            video_urls = [name for name in (getattr(video, "name", None) for video in videos) if name]

        return image_urls, video_urls

    def _create_signed_media_url(self, storage_path: str, expires_in: int = 3600) -> Optional[str]:
        try:
            response = supabase_client.storage.from_("media-uploads").create_signed_url(storage_path, expires_in)
            if isinstance(response, dict):
                return response.get("signedURL") or response.get("signed_url")
        except Exception as exc:
            logger.warning("MediaTools: failed to create signed URL for %s: %s", storage_path, exc)
        return None

    def _image_to_data_url(self, image: Image) -> Optional[str]:
        content = getattr(image, "content", None)
        if isinstance(content, str):
            stripped = content.strip()
            if stripped.startswith("data:"):
                return stripped
            try:
                base64.b64decode(stripped, validate=True)
                return f"data:image/png;base64,{stripped}"
            except (ValueError, binascii.Error):
                return None

        if isinstance(content, (bytes, bytearray)):
            return f"data:image/png;base64,{base64.b64encode(bytes(content)).decode('utf-8')}"

        url = getattr(image, "url", None)
        if isinstance(url, str) and url.strip():
            return url.strip()

        return None

    def _extract_generated_image(self, run_output: RunOutput) -> Tuple[bytes, str]:
        images = getattr(run_output, "images", None) or []
        if not images:
            raise RuntimeError("Image generation completed without an image in the Agno RunOutput.")

        for image in images:
            image_bytes, mime_type = self._extract_image_bytes(image)
            if image_bytes:
                return image_bytes, mime_type or "image/png"

        raise RuntimeError("Image generation completed, but the generated image could not be decoded.")

    def _extract_image_bytes(self, image: Image) -> Tuple[bytes, Optional[str]]:
        mime_type = str(
            getattr(image, "mime_type", None)
            or getattr(image, "media_type", None)
            or "image/png"
        )
        content = getattr(image, "content", None)

        if isinstance(content, (bytes, bytearray)):
            return bytes(content), mime_type

        if isinstance(content, str):
            stripped = content.strip()
            if stripped.startswith("data:"):
                return self._decode_data_url(stripped)
            try:
                return base64.b64decode(stripped), mime_type
            except (ValueError, binascii.Error):
                pass

        url = getattr(image, "url", None)
        if isinstance(url, str) and url.strip():
            if url.startswith("data:"):
                return self._decode_data_url(url)
            downloaded = requests.get(url, timeout=180)
            downloaded.raise_for_status()
            return downloaded.content, downloaded.headers.get("content-type") or mime_type

        return b"", None

    def _decode_data_url(self, data_url: str) -> Tuple[bytes, Optional[str]]:
        if not data_url.startswith("data:"):
            return b"", None
        header, _, payload = data_url.partition(",")
        mime_type = header[5:].split(";")[0] if ";" in header else header[5:]
        return base64.b64decode(payload), mime_type or None

    def _persist_generated_media(
        self,
        *,
        media_bytes: bytes,
        mime_type: str,
        media_kind: str,
        prompt: str,
        source_urls: List[str],
        provider_response: Dict[str, Any],
    ) -> Tuple[str, str, str]:
        artifact_id = str(uuid.uuid4())
        extension = self._extension_for_mime_type(mime_type=mime_type, media_kind=media_kind)
        file_name = f"generated-{media_kind}-{artifact_id}.{extension}"
        user_segment = self.user_id or "unknown-user"
        conversation_segment = self.conversation_id or "unknown-conversation"
        storage_path = f"{user_segment}/{conversation_segment}/generated/{file_name}"

        supabase_client.storage.from_("media-uploads").upload(
            storage_path,
            media_bytes,
            file_options={"content-type": mime_type},
        )

        signed_url = self._create_signed_media_url(storage_path, expires_in=3600)
        if not signed_url:
            raise RuntimeError("Generated media was uploaded but no signed URL could be created.")

        if self.conversation_id and self.user_id:
            persistence_service = get_persistence_service()
            persistence_service.register_content(
                session_id=self.conversation_id,
                user_id=self.user_id,
                content_type="upload",
                reference_id=artifact_id,
                message_id=self.message_id,
                metadata={
                    "filename": file_name,
                    "mime_type": mime_type,
                    "size": len(media_bytes),
                    "path": storage_path,
                    "isMedia": True,
                    "is_text": False,
                    "is_generated": True,
                    "artifact_type": media_kind,
                    "provider": "openrouter",
                    "model": IMAGE_MODEL_ID if media_kind == "image" else VIDEO_MODEL_ID,
                    "prompt": prompt,
                    "source_urls": source_urls,
                    "provider_response": {
                        "id": provider_response.get("id"),
                        "status": provider_response.get("status"),
                        "generation_id": provider_response.get("generation_id"),
                        "model": provider_response.get("model"),
                    },
                },
            )

        return artifact_id, signed_url, file_name

    def _emit_media_generated(
        self,
        *,
        artifact_id: str,
        media_type: str,
        media_url: str,
        mime_type: str,
        file_name: str,
    ) -> None:
        if not self.socketio or not self.conversation_id:
            return
        payload = {
            "id": self.message_id,
            "artifactId": artifact_id,
            "conversationId": self.conversation_id,
            "mediaType": media_type,
            "mediaUrl": media_url,
            "mimeType": mime_type,
            "fileName": file_name,
            "agent_name": "MediaTools",
        }
        self.socketio.emit("media_generated", payload, room=f"conv:{self.conversation_id}")

    def _poll_video_job(self, polling_url: str) -> Dict[str, Any]:
        started_at = time.time()
        while True:
            response = requests.get(
                polling_url,
                headers={"Authorization": f"Bearer {self.openrouter_api_key}"},
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
            status = str(payload.get("status") or "").strip().lower()
            if status == "completed":
                return payload
            if status in {"failed", "cancelled", "expired"}:
                raise RuntimeError(payload.get("error") or f"Video generation ended with status '{status}'.")
            if time.time() - started_at > 900:
                raise TimeoutError("Video generation timed out after 15 minutes.")
            time.sleep(5)

    def _extension_for_mime_type(self, *, mime_type: str, media_kind: str) -> str:
        if mime_type == "image/png":
            return "png"
        if mime_type == "image/jpeg":
            return "jpg"
        if mime_type == "image/webp":
            return "webp"
        if mime_type == "video/mp4":
            return "mp4"
        return "png" if media_kind == "image" else "mp4"
