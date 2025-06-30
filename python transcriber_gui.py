import os
import threading
import ffmpeg
from pathlib import Path
from faster_whisper import WhisperModel
import deepl
import customtkinter as ctk
from tkinter import filedialog, messagebox, StringVar, OptionMenu


def format_timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def extract_audio(video_path, output_path="temp_audio.wav"):
    try:
        ffmpeg.input(video_path).output(output_path, ac=1, ar=16000, vn=None).overwrite_output().run(quiet=True)
        return output_path
    except Exception as e:
        messagebox.showerror("Ошибка", f"Ошибка при извлечении аудио: {e}")
        return None


def transcribe_with_translation(input_file, translator_choice, gui_callback=None, api_key="69999737-95c3-440e-84bc-96fb8550f83a:fx"):
    input_path = Path(input_file)
    base_path = input_path.with_suffix("")

    if input_path.suffix.lower() != ".wav":
        audio_path = "temp_audio.wav"
        extract_audio(str(input_path), audio_path)
        temp_created = True
    else:
        audio_path = str(input_path)
        temp_created = False

    try:
        model = WhisperModel("large-v3", device="cuda", compute_type="float16")
        segments, _ = model.transcribe(audio_path, beam_size=5, language="en")

        en_path = base_path.with_name(base_path.name + "_en.srt")
        ru_path = base_path.with_name(base_path.name + "_ru.srt")

        if translator_choice == "DeepL":
            translator = deepl.Translator(api_key)
        else:
            translator = None  # fallback for manual/no translation

        with open(en_path, "w", encoding="utf-8") as en_file, \
             open(ru_path, "w", encoding="utf-8") as ru_file:

            for i, segment in enumerate(segments, start=1):
                start = format_timestamp(segment.start)
                end = format_timestamp(segment.end)
                text = segment.text.strip()

                if translator:
                    try:
                        translated = translator.translate_text(text, target_lang="RU").text
                    except Exception as e:
                        translated = f"Ошибка перевода: {e}"
                else:
                    translated = text

                en_file.write(f"{i}\n{start} --> {end}\n{text}\n\n")
                ru_file.write(f"{i}\n{start} --> {end}\n{translated}\n\n")

        if gui_callback:
            gui_callback(f"✅ Субтитры сохранены:\n{en_path.name}\n{ru_path.name}")
    finally:
        if temp_created and os.path.exists("temp_audio.wav"):
            os.remove("temp_audio.wav")


# --- Интерфейс ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.geometry("500x350")
app.title("🎧 Whisper + Переводчик")

label = ctk.CTkLabel(app, text="Выберите видео или аудиофайл", font=("Arial", 16))
label.pack(pady=20)

status_label = ctk.CTkLabel(app, text="", font=("Arial", 14), wraplength=400)
status_label.pack(pady=10)

translator_var = StringVar(value="DeepL")
translator_label = ctk.CTkLabel(app, text="Выберите переводчик:", font=("Arial", 14))
translator_label.pack()
translator_menu = OptionMenu(app, translator_var, "DeepL", "Без перевода")
translator_menu.pack(pady=5)

def browse_file():
    file_path = filedialog.askopenfilename(filetypes=[("Audio/Video files", "*.mp4 *.wav *.mkv *.mp3")])
    if file_path:
        status_label.configure(text="⏳ Обработка... Подождите.")
        threading.Thread(target=transcribe_with_translation, args=(file_path, translator_var.get(), set_status)).start()


def set_status(text):
    status_label.configure(text=text)


btn = ctk.CTkButton(app, text="Выбрать файл", command=browse_file)
btn.pack(pady=10)

app.mainloop()
