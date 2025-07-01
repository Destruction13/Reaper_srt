# Whisper Translator GUI

This project provides a desktop application built with **PySide6** for transcribing audio or video files using `faster-whisper`. Optionally, it can translate subtitles via several online services.

## Features
- Choose among multiple translators, including free and paid APIs
- Select source and target languages via dropdowns
- Progress bar while transcribing/translating
- API keys stored in `~/.my_translator_app/api_keys.json`
- Works with common video and audio formats

## Requirements
Install dependencies with:
```bash
pip install -r requirements.txt
```

You also need `ffmpeg` in your system `PATH` for audio extraction.

## Usage
Run the application using Python:
```bash
python transcriber_pyside6.py
```
On Windows you can simply double-click `run_transcriber.bat`.
