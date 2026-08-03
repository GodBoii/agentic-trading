import argparse
import json
import os
import shutil
import sys
import urllib.request
import wave
import zipfile


DEFAULT_MODEL_NAME = "vosk-model-small-en-us-0.15"
DEFAULT_MODEL_URL = f"https://alphacephei.com/vosk/models/{DEFAULT_MODEL_NAME}.zip"


def emit(payload):
    print(json.dumps(payload), flush=True)


def is_valid_model_dir(path):
    if not path or not os.path.isdir(path):
        return False
    required = ("am", "conf", "graph", "ivector")
    return all(os.path.exists(os.path.join(path, name)) for name in required)


def find_model(model_root, model_name=DEFAULT_MODEL_NAME):
    candidates = [
        os.path.join(model_root, model_name),
        model_root,
    ]
    for candidate in candidates:
        if is_valid_model_dir(candidate):
            return candidate

    if os.path.isdir(model_root):
        for entry in os.listdir(model_root):
            candidate = os.path.join(model_root, entry)
            if is_valid_model_dir(candidate):
                return candidate
    return None


def download_model(model_root, url=DEFAULT_MODEL_URL, model_name=DEFAULT_MODEL_NAME):
    os.makedirs(model_root, exist_ok=True)
    existing = find_model(model_root, model_name)
    if existing:
        emit({"type": "complete", "modelPath": existing, "alreadyExists": True})
        return existing

    zip_path = os.path.join(model_root, f"{model_name}.zip")
    temp_extract_dir = os.path.join(model_root, f".{model_name}.tmp")
    final_model_dir = os.path.join(model_root, model_name)

    if os.path.isdir(temp_extract_dir):
        shutil.rmtree(temp_extract_dir, ignore_errors=True)
    os.makedirs(temp_extract_dir, exist_ok=True)

    last_progress = {"value": -1}

    def report_progress(block_count, block_size, total_size):
        downloaded = block_count * block_size
        progress = 0 if total_size <= 0 else min(100, round((downloaded / total_size) * 100))
        if progress == last_progress["value"]:
            return
        last_progress["value"] = progress
        emit({
            "type": "progress",
            "progress": progress,
            "downloaded": min(downloaded, total_size) if total_size > 0 else downloaded,
            "total": total_size,
        })

    try:
        emit({"type": "status", "message": "downloading"})
        urllib.request.urlretrieve(url, zip_path, report_progress)

        emit({"type": "status", "message": "extracting"})
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(temp_extract_dir)

        extracted_model = find_model(temp_extract_dir, model_name)
        if not extracted_model:
            raise RuntimeError("Downloaded archive did not contain a valid Vosk model.")

        if os.path.isdir(final_model_dir):
            shutil.rmtree(final_model_dir, ignore_errors=True)
        shutil.move(extracted_model, final_model_dir)

        emit({"type": "complete", "modelPath": final_model_dir, "alreadyExists": False})
        return final_model_dir
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)
        if os.path.isdir(temp_extract_dir):
            shutil.rmtree(temp_extract_dir, ignore_errors=True)


def transcribe_wav(model_path, wav_path, grammar=None):
    from vosk import KaldiRecognizer, Model, SetLogLevel

    SetLogLevel(-1)

    if not is_valid_model_dir(model_path):
        raise RuntimeError(f"Vosk model not found or incomplete: {model_path}")

    with wave.open(wav_path, "rb") as wav_file:
        if wav_file.getnchannels() != 1:
            raise RuntimeError("Audio must be mono.")
        if wav_file.getsampwidth() != 2:
            raise RuntimeError("Audio must be 16-bit PCM.")

        sample_rate = wav_file.getframerate()
        model = Model(model_path)
        if grammar:
            recognizer = KaldiRecognizer(model, sample_rate, json.dumps(grammar))
        else:
            recognizer = KaldiRecognizer(model, sample_rate)
        recognizer.SetWords(True)

        segments = []
        while True:
            data = wav_file.readframes(4000)
            if not data:
                break
            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result() or "{}")
                if result.get("text"):
                    segments.append(result)

        final_result = json.loads(recognizer.FinalResult() or "{}")
        if final_result.get("text"):
            segments.append(final_result)

    text = " ".join(segment.get("text", "") for segment in segments).strip()
    words = []
    for segment in segments:
        words.extend(segment.get("result") or [])

    emit({
        "type": "result",
        "text": text,
        "words": words,
        "sampleRate": sample_rate,
    })


def main():
    parser = argparse.ArgumentParser(description="Aetheria Vosk STT helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--model-root", required=True)
    status_parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)

    download_parser = subparsers.add_parser("download-model")
    download_parser.add_argument("--model-root", required=True)
    download_parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    download_parser.add_argument("--url", default=DEFAULT_MODEL_URL)

    transcribe_parser = subparsers.add_parser("transcribe")
    transcribe_parser.add_argument("--model-path", required=True)
    transcribe_parser.add_argument("--wav", required=True)
    transcribe_parser.add_argument("--grammar-json", default="")

    args = parser.parse_args()

    try:
        if args.command == "status":
            model_path = find_model(args.model_root, args.model_name)
            emit({"type": "status", "ready": bool(model_path), "modelPath": model_path})
        elif args.command == "download-model":
            download_model(args.model_root, args.url, args.model_name)
        elif args.command == "transcribe":
            grammar = json.loads(args.grammar_json) if args.grammar_json else None
            transcribe_wav(args.model_path, args.wav, grammar)
    except Exception as error:
        emit({"type": "error", "error": str(error)})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
