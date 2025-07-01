import os
import sys
import json
import subprocess
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QFileDialog,
    QLineEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QProgressBar,
)
from PySide6.QtCore import Qt, QThread, Signal

from faster_whisper import WhisperModel
import requests

BASE_DIR = Path(os.path.dirname(sys.argv[0]))
KEYS_PATH = BASE_DIR / "api_keys.json"

FREE_TRANSLATORS = [
    "Без перевода",
    "LibreTranslate",
    "Google Translate Free API",
    "MyMemory",
    "OpenAI Whisper internal",
]
PAID_TRANSLATORS = [
    "DeepL",
    "Google Cloud Translation",
    "Microsoft Azure Translate",
]
ALL_TRANSLATORS = FREE_TRANSLATORS + PAID_TRANSLATORS

LANGUAGES = {
    "en": "English",
    "ru": "Russian",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
}

def load_api_keys():
    if KEYS_PATH.exists():
        try:
            with open(KEYS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_api_keys(keys):
    KEYS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(KEYS_PATH, "w", encoding="utf-8") as f:
        json.dump(keys, f, ensure_ascii=False, indent=2)

class APIKeyDialog(QDialog):
    def __init__(self, translator_name, keys, parent=None):
        super().__init__(parent)
        self.setWindowTitle("API Key")
        self.translator = translator_name
        self.keys = keys
        layout = QFormLayout(self)
        self.key_edit = QLineEdit()
        existing = ""
        if isinstance(self.keys.get(translator_name), dict):
            existing = self.keys.get(translator_name, {}).get("key", "")
        else:
            existing = self.keys.get(translator_name, "")
        self.key_edit.setText(existing)
        layout.addRow(QLabel(f"API ключ для {translator_name}"), self.key_edit)
        self.region_edit = None
        if translator_name == "Microsoft Azure Translate":
            self.region_edit = QLineEdit()
            existing_region = ""
            if isinstance(self.keys.get(translator_name), dict):
                existing_region = self.keys.get(translator_name, {}).get("region", "")
            self.region_edit.setText(existing_region)
            layout.addRow(QLabel("Регион Azure"), self.region_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def accept(self):
        value = self.key_edit.text().strip()
        if self.region_edit:
            region = self.region_edit.text().strip()
            self.keys[self.translator] = {"key": value, "region": region}
        else:
            self.keys[self.translator] = value
        save_api_keys(self.keys)
        super().accept()

class SettingsDialog(QDialog):
    def __init__(self, keys, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки API")
        self.keys = keys
        layout = QFormLayout(self)
        self.translator_combo = QComboBox()
        self.translator_combo.addItems(PAID_TRANSLATORS)
        layout.addRow(QLabel("Переводчик"), self.translator_combo)
        self.key_edit = QLineEdit()
        layout.addRow(QLabel("API ключ"), self.key_edit)
        self.region_edit = QLineEdit()
        self.region_edit.setPlaceholderText("Регион для Azure")
        layout.addRow(QLabel("Регион"), self.region_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self.translator_combo.currentTextChanged.connect(self.load_existing)
        self.load_existing(self.translator_combo.currentText())

    def load_existing(self, name):
        entry = self.keys.get(name)
        if isinstance(entry, dict):
            self.key_edit.setText(entry.get("key", ""))
            self.region_edit.setText(entry.get("region", ""))
        else:
            self.key_edit.setText(entry or "")
            self.region_edit.setText("")
        self.region_edit.setVisible(name == "Microsoft Azure Translate")

    def save(self):
        name = self.translator_combo.currentText()
        key = self.key_edit.text().strip()
        if name == "Microsoft Azure Translate":
            region = self.region_edit.text().strip()
            self.keys[name] = {"key": key, "region": region}
        else:
            self.keys[name] = key
        save_api_keys(self.keys)
        self.accept()

class TranscribeThread(QThread):
    progress = Signal(str)
    finished = Signal(str)

    def __init__(self, file_path, translator, src_lang, tgt_lang, keys):
        super().__init__()
        self.file_path = file_path
        self.translator = translator
        self.src_lang = src_lang
        self.tgt_lang = tgt_lang
        self.keys = keys

    def run(self):
        msg = transcribe_with_translation(
            self.file_path,
            self.translator,
            self.src_lang,
            self.tgt_lang,
            self.keys,
            gui_callback=self.progress.emit,
        )
        self.finished.emit(msg)

def extract_audio(video_path, output_path):
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-ac",
        "1",
        "-ar",
        "16000",
        output_path,
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_path
    except Exception as e:
        return None

def format_timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

def translate_text(translator_name, text, src_lang, tgt_lang, keys):
    if translator_name in ("Без перевода", "OpenAI Whisper internal"):
        return text
    if translator_name == "LibreTranslate":
        try:
            resp = requests.post(
                "https://libretranslate.de/translate",
                data={"q": text, "source": src_lang, "target": tgt_lang},
                timeout=30,
            )
            if resp.ok:
                return resp.json().get("translatedText", text)
        except Exception:
            pass
        return text
    if translator_name == "MyMemory":
        try:
            resp = requests.get(
                "https://api.mymemory.translated.net/get",
                params={"q": text, "langpair": f"{src_lang}|{tgt_lang}"},
                timeout=30,
            )
            if resp.ok:
                data = resp.json()
                return data.get("responseData", {}).get("translatedText", text)
        except Exception:
            pass
        return text
    if translator_name == "Google Translate Free API":
        try:
            resp = requests.get(
                "https://translate.googleapis.com/translate_a/single",
                params={
                    "client": "gtx",
                    "sl": src_lang,
                    "tl": tgt_lang,
                    "dt": "t",
                    "q": text,
                },
                timeout=30,
            )
            if resp.ok:
                data = resp.json()
                return "".join(part[0] for part in data[0])
        except Exception:
            pass
        return text
    if translator_name == "DeepL":
        key = keys.get("DeepL")
        if not key:
            return text
        try:
            resp = requests.post(
                "https://api-free.deepl.com/v2/translate",
                data={
                    "auth_key": key,
                    "text": text,
                    "source_lang": src_lang.upper(),
                    "target_lang": tgt_lang.upper(),
                },
                timeout=30,
            )
            if resp.ok:
                return resp.json()["translations"][0]["text"]
        except Exception:
            pass
        return text
    if translator_name == "Google Cloud Translation":
        key = keys.get("Google Cloud Translation")
        if not key:
            return text
        try:
            resp = requests.post(
                f"https://translation.googleapis.com/language/translate/v2?key={key}",
                data={
                    "q": text,
                    "source": src_lang,
                    "target": tgt_lang,
                    "format": "text",
                },
                timeout=30,
            )
            if resp.ok:
                return resp.json()["data"]["translations"][0]["translatedText"]
        except Exception:
            pass
        return text
    if translator_name == "Microsoft Azure Translate":
        entry = keys.get("Microsoft Azure Translate")
        if not isinstance(entry, dict):
            return text
        key = entry.get("key")
        region = entry.get("region", "global")
        if not key:
            return text
        headers = {
            "Ocp-Apim-Subscription-Key": key,
            "Ocp-Apim-Subscription-Region": region,
            "Content-type": "application/json",
        }
        try:
            resp = requests.post(
                f"https://api.cognitive.microsofttranslator.com/translate?api-version=3.0&from={src_lang}&to={tgt_lang}",
                headers=headers,
                json=[{"Text": text}],
                timeout=30,
            )
            if resp.ok:
                return resp.json()[0]["translations"][0]["text"]
        except Exception:
            pass
        return text
    return text

def transcribe_with_translation(input_file, translator_choice, src_lang, tgt_lang, keys, gui_callback=None):
    input_path = Path(input_file)
    base_path = (BASE_DIR / input_path.stem)
    if input_path.suffix.lower() != ".wav":
        audio_path = str(BASE_DIR / "temp_audio.wav")
        extract_audio(str(input_path), audio_path)
        temp_created = True
    else:
        audio_path = str(input_path)
        temp_created = False

    try:
        device = "cuda" if os.environ.get("CUDA_VISIBLE_DEVICES") else "cpu"
        compute = "float16" if device == "cuda" else "int8"
        model = WhisperModel("base", device=device, compute_type=compute)
        if translator_choice == "OpenAI Whisper internal":
            segments, _ = model.transcribe(audio_path, beam_size=5, language=src_lang, task="translate")
            out_path = base_path.with_name(base_path.name + f"_{tgt_lang}.srt")
            with open(out_path, "w", encoding="utf-8") as out_file:
                for i, segment in enumerate(segments, start=1):
                    start = format_timestamp(segment.start)
                    end = format_timestamp(segment.end)
                    text = segment.text.strip()
                    out_file.write(f"{i}\n{start} --> {end}\n{text}\n\n")
                    if gui_callback:
                        gui_callback(f"Segment {i}")
            return f"✅ Субтитры сохранены:\n{out_path}"
        else:
            segments, _ = model.transcribe(audio_path, beam_size=5, language=src_lang)
            src_path = base_path.with_name(base_path.name + f"_{src_lang}.srt")
            tgt_path = base_path.with_name(base_path.name + f"_{tgt_lang}.srt")
            with open(src_path, "w", encoding="utf-8") as src_file, open(tgt_path, "w", encoding="utf-8") as tgt_file:
                for i, segment in enumerate(segments, start=1):
                    start = format_timestamp(segment.start)
                    end = format_timestamp(segment.end)
                    text = segment.text.strip()
                    src_file.write(f"{i}\n{start} --> {end}\n{text}\n\n")
                    translated = translate_text(translator_choice, text, src_lang, tgt_lang, keys)
                    tgt_file.write(f"{i}\n{start} --> {end}\n{translated}\n\n")
                    if gui_callback:
                        gui_callback(f"Segment {i}")
            return f"✅ Субтитры сохранены:\n{src_path}\n{tgt_path}"
    finally:
        if temp_created:
            temp_audio = BASE_DIR / "temp_audio.wav"
            if temp_audio.exists():
                temp_audio.unlink()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Whisper Transcriber")
        self.resize(600, 450)

        self.setStyleSheet(
            """
            QWidget { background-color: #2b2b2b; color: #ffffff; font-size: 14px; }
            QComboBox, QLineEdit { background-color: #444444; border: 1px solid #555555; padding: 4px; }
            QPushButton { background-color: #444444; border: 1px solid #555555; padding: 6px 12px; }
            QPushButton:hover { border-color: #888888; background-color: #555555; }
            QProgressBar { background-color: #3a3a3a; border: 1px solid #555; text-align: center; }
            QProgressBar::chunk { background-color: #607d8b; }
            """
        )

        self.api_keys = load_api_keys()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.label = QLabel("Выберите видео или аудиофайл")
        layout.addWidget(self.label)

        self.translator_combo = QComboBox()
        self.translator_combo.addItems(ALL_TRANSLATORS)
        layout.addWidget(self.translator_combo)

        lang_layout = QHBoxLayout()
        self.src_combo = QComboBox()
        self.tgt_combo = QComboBox()
        for code, name in LANGUAGES.items():
            display = f"{code} - {name}"
            self.src_combo.addItem(display, code)
            self.tgt_combo.addItem(display, code)
        self.src_combo.setCurrentIndex(0)
        if "ru" in LANGUAGES:
            self.tgt_combo.setCurrentIndex(list(LANGUAGES.keys()).index("ru"))
        lang_layout.addWidget(QLabel("Исходный язык"))
        lang_layout.addWidget(self.src_combo)
        lang_layout.addWidget(QLabel("Язык перевода"))
        lang_layout.addWidget(self.tgt_combo)
        layout.addLayout(lang_layout)

        btn_layout = QHBoxLayout()
        self.button = QPushButton("Выбрать файл")
        self.settings_btn = QPushButton("Настройки API")
        btn_layout.addWidget(self.button)
        btn_layout.addWidget(self.settings_btn)
        layout.addLayout(btn_layout)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.button.clicked.connect(self.choose_file)
        self.settings_btn.clicked.connect(self.open_settings)
        self.translator_combo.currentTextChanged.connect(self.check_api_key)

    def check_api_key(self, name):
        if name in PAID_TRANSLATORS:
            entry = self.api_keys.get(name)
            if not entry:
                dialog = APIKeyDialog(name, self.api_keys, self)
                dialog.exec()

    def open_settings(self):
        dlg = SettingsDialog(self.api_keys, self)
        dlg.exec()

    def choose_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выбор файла",
            "",
            "Audio/Video Files (*.mp4 *.mp3 *.mkv *.wav *.flac *.avi);;All Files (*)",
        )
        if file_path:
            translator = self.translator_combo.currentText()
            src = self.src_combo.currentData()
            tgt = self.tgt_combo.currentData()
            self.progress.setRange(0, 0)
            self.progress.setVisible(True)
            self.status.setText("⏳ Обработка... Подождите.")
            self.worker = TranscribeThread(file_path, translator, src, tgt, self.api_keys)
            self.worker.progress.connect(self.update_status)
            self.worker.finished.connect(self.finish_processing)
            self.worker.start()

    def update_status(self, text):
        self.status.setText(text)

    def finish_processing(self, msg):
        self.progress.setVisible(False)
        self.progress.setRange(0, 1)
        self.status.setText(msg)
        save_api_keys(self.api_keys)

if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()
