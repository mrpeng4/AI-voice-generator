import asyncio
import json
import os
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
import urllib.request

import customtkinter as ctk
import edge_tts
import pygame


# --- Network Check ---
def has_internet():
    try:
        urllib.request.urlopen("https://www.google.com", timeout=3)
        return True
    except Exception:
        return False


if not has_internet():
    root = ctk.CTk()
    root.withdraw()
    messagebox.showerror(
        "No Internet",
        "This app requires an internet connection to work.\nPlease check your connection and try again."
    )
    sys.exit()

# Set initial appearance and default color theme
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

# --- Application Folders & Constants ---
appdata = os.getenv('APPDATA') or os.path.expanduser('~')
APP_FOLDER = os.path.join(appdata, 'AI_Voice_Generator')
os.makedirs(APP_FOLDER, exist_ok=True)

FAVORITES_FILE = os.path.join(APP_FOLDER, "favorite_voices.json")
RECENT_EXPORTS_FILE = os.path.join(APP_FOLDER, "recent_exports.json")


# --- Utility Functions ---
def load_favorites():
    if os.path.exists(FAVORITES_FILE):
        with open(FAVORITES_FILE, "r") as f:
            return json.load(f)
    return []


def save_favorites(favorites):
    with open(FAVORITES_FILE, "w") as f:
        json.dump(favorites, f)


def load_recent_exports():
    if os.path.exists(RECENT_EXPORTS_FILE):
        with open(RECENT_EXPORTS_FILE, "r") as f:
            return json.load(f)
    return []


def save_recent_export(path):
    exports = load_recent_exports()
    exports.insert(0, {
        "file": path,
        "time": time.strftime("%Y-%m-%d %H:%M:%S")
    })
    exports = exports[:10]  # Limit to last 10
    with open(RECENT_EXPORTS_FILE, "w") as f:
        json.dump(exports, f, indent=2)


def chunk_text(text, max_len=3000):
    sentences = text.split('. ')
    chunks, current = [], ''
    for sentence in sentences:
        sentence += '. '
        if len(current) + len(sentence) <= max_len:
            current += sentence
        else:
            chunks.append(current.strip())
            current = sentence
    if current:
        chunks.append(current.strip())
    return chunks


import re

# Matches "Name:" at the start of a line, where Name is short and has no digits —
# avoids false splits on things like times ("10:30") or URLs.
SPEAKER_LINE_RE = re.compile(r"^\s*([A-Za-z][A-Za-z .'\-]{0,24}?)\s*:\s*(.*)$")


def format_voice_name(voice):
    """Turn a raw voice dict into a clean 'Name (Place)' label for display."""
    short_name = voice.get("ShortName", "")
    friendly = voice.get("FriendlyName", "")

    # Name: take the part of ShortName after the locale, strip the Neural suffix,
    # and split CamelCase into separate words (AriaNeural -> Aria, JennyMultilingualNeural -> Jenny Multilingual).
    name_part = short_name.split("-")[-1]
    name_part = re.sub(r"Neural$", "", name_part)
    name_part = re.sub(r"(?<!^)(?=[A-Z])", " ", name_part).strip()
    if not name_part:
        name_part = short_name

    # Place: pull the last "(...)" group out of FriendlyName, e.g.
    # "Microsoft Aria Online (Natural) - English (United States)" -> "United States".
    place = ""
    matches = re.findall(r"\(([^)]+)\)", friendly)
    if matches:
        place = matches[-1]
    if not place:
        locale = voice.get("Locale", "")
        place = locale.split("-")[-1] if locale else ""

    return f"{name_part} ({place})" if place else name_part


def build_voice_maps(voices):
    """Return (sorted display names, display->ShortName map, ShortName->display map)."""
    display_to_short = {}
    short_to_display = {}
    for v in voices:
        short = v["ShortName"]
        display = format_voice_name(v)
        # Guard against duplicate display names colliding
        if display in display_to_short and display_to_short[display] != short:
            display = f"{display} [{short}]"
        display_to_short[display] = short
        short_to_display[short] = display
    return sorted(display_to_short.keys()), display_to_short, short_to_display


# --- UI Pages ---

class RecentExportsPage:
    def __init__(self, root, voices):
        self.root = root
        self.voices = voices

        self.frame = ctk.CTkFrame(root)
        self.frame.pack(expand=True, fill="both", padx=20, pady=20)

        ctk.CTkLabel(self.frame, text="📂 Recent Exports", font=("Segoe UI", 20, "bold")).pack(pady=15)

        self.textbox = ctk.CTkTextbox(self.frame, font=("Segoe UI", 12))
        self.textbox.pack(padx=20, pady=10, fill="both", expand=True)

        exports = load_recent_exports()
        if not exports:
            self.textbox.insert("1.0", "No recent exports found.")
        else:
            display_text = "\n".join([f"{exp['time']}  —  {exp['file']}" for exp in exports])
            self.textbox.insert("1.0", display_text)

        self.textbox.configure(state="disabled")

        ctk.CTkButton(self.frame, text="🔙 Back", font=("Segoe UI", 13), command=self.back).pack(pady=15)

    def back(self):
        self.frame.destroy()
        StartPage(self.root, self.voices)


class StartPage:
    def __init__(self, root, voices):
        self.root = root
        self.voices = voices

        self.frame = ctk.CTkFrame(root, fg_color="transparent")
        self.frame.pack(expand=True, fill="both", padx=40, pady=30)

        # --- Header ---
        header = ctk.CTkFrame(self.frame, fg_color="transparent")
        header.pack(pady=(10, 25))
        ctk.CTkLabel(header, text="🎙 AI Voice Generator", font=("Segoe UI", 30, "bold")).pack()
        ctk.CTkLabel(header, text="Turn text into natural speech with 1 or many voices",
                     font=("Segoe UI", 13), text_color=("gray30", "gray70")).pack(pady=(4, 0))

        # --- Card: main modes ---
        card = ctk.CTkFrame(self.frame, corner_radius=14)
        card.pack(pady=10, padx=10, fill="x")

        ctk.CTkLabel(card, text="GET STARTED", font=("Segoe UI", 11, "bold"),
                     text_color=("gray40", "gray60")).pack(pady=(15, 5))

        ctk.CTkButton(card, text="🎤  Single Voice Mode", font=("Segoe UI", 14, "bold"), width=300, height=44,
                      corner_radius=10, command=self.start_single).pack(pady=(5, 8))

        ctk.CTkButton(card, text="🎭  Multi Voice Mode", font=("Segoe UI", 14, "bold"), width=300, height=44,
                      corner_radius=10, command=self.start_multi).pack(pady=8)

        ctk.CTkButton(card, text="🎓  Start Tutorial", font=("Segoe UI", 13, "bold"), width=300, height=40,
                      corner_radius=10, fg_color="#2FA572", hover_color="#268a5f",
                      command=self.start_tutorial).pack(pady=(8, 18))

        # --- Card: library/tools ---
        tools_card = ctk.CTkFrame(self.frame, corner_radius=14)
        tools_card.pack(pady=(15, 10), padx=10, fill="x")

        ctk.CTkLabel(tools_card, text="LIBRARY", font=("Segoe UI", 11, "bold"),
                     text_color=("gray40", "gray60")).pack(pady=(15, 5))

        row = ctk.CTkFrame(tools_card, fg_color="transparent")
        row.pack(pady=(5, 18))
        ctk.CTkButton(row, text="⭐ Favorite Voices", font=("Segoe UI", 13), width=195, height=36,
                      fg_color="transparent", border_width=1, command=self.open_favorites).grid(
            row=0, column=0, padx=6)
        ctk.CTkButton(row, text="📂 Recent Exports", font=("Segoe UI", 13), width=195, height=36,
                      fg_color="transparent", border_width=1, command=self.open_recent_exports).grid(
            row=0, column=1, padx=6)

        # --- Footer ---
        footer = ctk.CTkFrame(self.frame, fg_color="transparent")
        footer.pack(side="bottom", pady=(15, 0))
        self.theme_btn = ctk.CTkButton(footer, text="🌓 Toggle Light/Dark Theme", font=("Segoe UI", 12), width=280,
                                       fg_color="transparent", border_width=1, command=self.toggle_theme)
        self.theme_btn.pack()

    def toggle_theme(self):
        current = ctk.get_appearance_mode()
        if current == "Dark":
            ctk.set_appearance_mode("Light")
        else:
            ctk.set_appearance_mode("Dark")

    def start_single(self):
        self.frame.destroy()
        SingleVoiceApp(self.root, self.voices)

    def start_multi(self):
        self.frame.destroy()
        MultiVoiceApp(self.root, self.voices)

    def open_favorites(self):
        self.frame.destroy()
        FavoritesPage(self.root, self.voices)

    def open_recent_exports(self):
        self.frame.destroy()
        RecentExportsPage(self.root, self.voices)

    def start_tutorial(self):
        self.frame.destroy()
        TutorialPage(self.root, self.voices)


class TutorialPage:
    """Step-by-step walkthrough of the app's features, launched from the start screen."""

    STEPS = [
        ("👋 Welcome", "This app turns text into spoken audio using natural AI voices.\n\n"
                        "This quick tutorial will walk you through every feature. "
                        "Use Next / Back to move around, or Skip at any time."),
        ("🎤 Single Voice Mode", "Type or paste text, pick one voice, and adjust Speed and Pitch "
                                  "with the sliders.\n\nPress 🔊 Speak to preview it out loud, or "
                                  "💾 Save MP3 to export the audio to a file."),
        ("⭐ Favorites", "Click the star next to the voice dropdown to save it as a favorite. "
                          "Favorites show up in their own quick-select dropdown so you don't have "
                          "to search the full voice list every time."),
        ("🎭 Multi Voice Mode", "Build a script with multiple lines, each with its own voice, speed "
                                 "and pitch.\n\nUse ➕ Add Sentence to add rows, and the ⬆️⬇️ 📥 ❌ "
                                 "buttons on each row to reorder, clone, or delete it."),
        ("👥 Name-Based Split", "In Multi Voice Mode, paste a script formatted like:\n"
                                 "  Alice: Hello there!\n  Bob: Hi Alice!\n\n"
                                 "Add voices to the 'Voices to Use' box, then click 👥 Name-Based "
                                 "Auto Split — each speaker is automatically assigned a voice."),
        ("💾 Saving & Exports", "🔊 Speak All previews every row in order. 💾 Save All renders every "
                                 "row into a single MP3 file.\n\nEvery export you save is remembered "
                                 "under 📂 Recent Exports on the home screen."),
        ("✅ You're ready!", "That covers the basics. You can revisit this tutorial anytime from the "
                              "home screen.\n\nClick Finish to start creating."),
    ]

    def __init__(self, root, voices):
        self.root = root
        self.voices = voices
        self.step = 0

        self.frame = ctk.CTkFrame(root, fg_color="transparent")
        self.frame.pack(expand=True, fill="both", padx=50, pady=50)

        self.card = ctk.CTkFrame(self.frame, corner_radius=16)
        self.card.pack(expand=True, fill="both")

        self.progress = ctk.CTkProgressBar(self.card, width=400)
        self.progress.pack(pady=(30, 15))

        self.title_label = ctk.CTkLabel(self.card, text="", font=("Segoe UI", 22, "bold"))
        self.title_label.pack(pady=(5, 15))

        self.body_label = ctk.CTkLabel(self.card, text="", font=("Segoe UI", 14),
                                        wraplength=460, justify="left")
        self.body_label.pack(pady=10, padx=30, expand=True)

        nav = ctk.CTkFrame(self.card, fg_color="transparent")
        nav.pack(pady=(15, 30))

        self.skip_btn = ctk.CTkButton(nav, text="Skip Tutorial", width=120, fg_color="transparent",
                                      border_width=1, command=self.finish)
        self.skip_btn.grid(row=0, column=0, padx=8)

        self.back_btn = ctk.CTkButton(nav, text="⬅ Back", width=100, command=self.prev_step)
        self.back_btn.grid(row=0, column=1, padx=8)

        self.next_btn = ctk.CTkButton(nav, text="Next ➡", width=100, command=self.next_step)
        self.next_btn.grid(row=0, column=2, padx=8)

        self.render_step()

    def render_step(self):
        title, body = self.STEPS[self.step]
        self.title_label.configure(text=title)
        self.body_label.configure(text=body)
        self.progress.set((self.step + 1) / len(self.STEPS))
        self.back_btn.configure(state="disabled" if self.step == 0 else "normal")
        is_last = self.step == len(self.STEPS) - 1
        self.next_btn.configure(text="Finish ✅" if is_last else "Next ➡",
                                command=self.finish if is_last else self.next_step)

    def next_step(self):
        if self.step < len(self.STEPS) - 1:
            self.step += 1
            self.render_step()

    def prev_step(self):
        if self.step > 0:
            self.step -= 1
            self.render_step()

    def finish(self):
        self.frame.destroy()
        StartPage(self.root, self.voices)


class FavoritesPage:
    def __init__(self, root, voices):
        self.root = root
        self.voices = voices
        self.favorites = load_favorites()

        self.frame = ctk.CTkFrame(root)
        self.frame.pack(expand=True, fill="both", padx=20, pady=20)

        ctk.CTkLabel(self.frame, text="⭐ Select Favorite Voices", font=("Segoe UI", 20, "bold")).pack(pady=15)

        self.scroll_frame = ctk.CTkScrollableFrame(self.frame)
        self.scroll_frame.pack(padx=20, pady=10, fill="both", expand=True)

        self.checkboxes = {}
        _, _, short_to_display = build_voice_maps(voices)
        for short_name, display_name in sorted(short_to_display.items(), key=lambda kv: kv[1]):
            cb = ctk.CTkCheckBox(self.scroll_frame, text=display_name)
            cb.pack(anchor="w", pady=4, padx=10)
            if short_name in self.favorites:
                cb.select()
            self.checkboxes[short_name] = cb

        btn_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        btn_frame.pack(pady=10)

        ctk.CTkButton(btn_frame, text="💾 Save Favorites", command=self.save_favorites).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="🔙 Back", command=self.back).pack(side="left", padx=10)

    def save_favorites(self):
        selected = [name for name, cb in self.checkboxes.items() if cb.get() == 1]
        save_favorites(selected)
        messagebox.showinfo("Saved", "Favorites updated successfully.")

    def back(self):
        self.frame.destroy()
        StartPage(self.root, self.voices)


class SingleVoiceApp:
    def __init__(self, root, voices):
        self.root = root
        self.voices = voices
        self.favorites = load_favorites()
        self.stop_requested = False
        self.all_display_names, self.display_to_short, self.short_to_display = build_voice_maps(voices)

        self.speed = tk.DoubleVar(value=1.0)
        self.pitch = tk.DoubleVar(value=1.0)

        self.frame = ctk.CTkFrame(root)
        self.frame.pack(fill="both", expand=True, padx=15, pady=15)

        self.text = ctk.CTkTextbox(self.frame, font=("Segoe UI", 12))
        self.text.pack(padx=15, pady=(15, 5), fill="both", expand=True)

        control_frame = ctk.CTkFrame(self.frame)
        control_frame.pack(pady=10, fill="x", padx=15)

        # Speed
        ctk.CTkLabel(control_frame, text="Speed:", font=("Segoe UI", 12)).grid(row=0, column=0, padx=5, pady=5)
        self.speed_slider = ctk.CTkSlider(control_frame, from_=0.5, to=2.0, number_of_steps=30, variable=self.speed,
                                          command=lambda val: self.update_speed_label())
        self.speed_slider.grid(row=0, column=1, padx=5, pady=5)
        self.speed_value_label = ctk.CTkLabel(control_frame, text=f"{self.speed.get():.2f}", font=("Segoe UI", 12))
        self.speed_value_label.grid(row=0, column=2, padx=(5, 15))

        # Pitch
        ctk.CTkLabel(control_frame, text="Pitch:", font=("Segoe UI", 12)).grid(row=0, column=3, padx=5, pady=5)
        self.pitch_slider = ctk.CTkSlider(control_frame, from_=0.5, to=2.0, number_of_steps=30, variable=self.pitch,
                                          command=lambda val: self.update_pitch_label())
        self.pitch_slider.grid(row=0, column=4, padx=5, pady=5)
        self.pitch_value_label = ctk.CTkLabel(control_frame, text=f"{self.pitch.get():.2f}", font=("Segoe UI", 12))
        self.pitch_value_label.grid(row=0, column=5, padx=(5, 15))

        reset_btn = ctk.CTkButton(control_frame, text="Reset", width=60, font=("Segoe UI", 11),
                                  command=self.reset_speed_pitch)
        reset_btn.grid(row=0, column=6, padx=5)

        # Voice Selection
        voice_frame = ctk.CTkFrame(self.frame)
        voice_frame.pack(pady=5, fill="x", padx=15)

        ctk.CTkLabel(voice_frame, text="Select Voice:", font=("Segoe UI", 12)).pack(side="left", padx=10)

        fav_display = [self.short_to_display[s] for s in self.favorites if s in self.short_to_display]

        self.voice_dropdown = ctk.CTkOptionMenu(voice_frame, values=self.all_display_names, width=300)
        self.voice_dropdown.set(fav_display[0] if fav_display else self.all_display_names[0])
        self.voice_dropdown.pack(side="left", padx=5, pady=5)

        ctk.CTkLabel(voice_frame, text="Favorites:", font=("Segoe UI", 12)).pack(side="left", padx=(20, 5))
        self.favorite_dropdown = ctk.CTkOptionMenu(voice_frame, values=fav_display if fav_display else ["None"],
                                                   command=self.on_favorite_selected)
        if fav_display:
            self.favorite_dropdown.set(fav_display[0])
        self.favorite_dropdown.pack(side="left", padx=5, pady=5)

        self._current_short = lambda: self.display_to_short.get(self.voice_dropdown.get(), self.voice_dropdown.get())

        self.star_btn = ctk.CTkButton(voice_frame, text="⭐" if self._current_short() in self.favorites else "☆",
                                      width=40, command=self.toggle_favorite)
        self.star_btn.pack(side="left", padx=10)

        # Action Buttons
        btn_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        btn_frame.pack(pady=15)

        ctk.CTkButton(btn_frame, text="🔊 Speak", command=self.speak).grid(row=0, column=0, padx=10)
        ctk.CTkButton(btn_frame, text="💾 Save MP3", command=self.save_mp3).grid(row=0, column=1, padx=10)
        ctk.CTkButton(btn_frame, text="⏹ Stop", fg_color="transparent", border_width=1, command=self.stop_audio).grid(
            row=0, column=2, padx=10)

        ctk.CTkButton(self.frame, text="🔙 Back to Home", fg_color="transparent", border_width=1,
                      command=self.back_to_home).pack(pady=5)

    def update_speed_label(self):
        self.speed_value_label.configure(text=f"{self.speed.get():.2f}")

    def update_pitch_label(self):
        self.pitch_value_label.configure(text=f"{self.pitch.get():.2f}")

    def reset_speed_pitch(self):
        self.speed.set(1.0)
        self.pitch.set(1.0)
        self.update_speed_label()
        self.update_pitch_label()

    def on_favorite_selected(self, choice):
        if choice and choice != "None":
            self.voice_dropdown.set(choice)
            self.star_btn.configure(text="⭐")

    def toggle_favorite(self):
        voice_short = self._current_short()
        if voice_short in self.favorites:
            self.favorites.remove(voice_short)
            self.star_btn.configure(text="☆")
        else:
            self.favorites.append(voice_short)
            self.star_btn.configure(text="⭐")

        fav_display = [self.short_to_display[s] for s in self.favorites if s in self.short_to_display]
        if fav_display:
            self.favorite_dropdown.configure(values=fav_display)
            self.favorite_dropdown.set(fav_display[0])
        else:
            self.favorite_dropdown.configure(values=["None"])
            self.favorite_dropdown.set("None")
        save_favorites(self.favorites)

    def speak(self):
        text = self.text.get("1.0", "end-1c").strip()
        voice = self._current_short()
        if not text or not voice:
            return
        self.stop_requested = False
        threading.Thread(target=self.run_speak_async, args=(text, voice), daemon=True).start()

    def show_generating_popup(self):
        self.generating_popup = ctk.CTkToplevel(self.root)
        self.generating_popup.title("Please wait")
        self.generating_popup.geometry("300x120")
        self.generating_popup.resizable(False, False)
        self.generating_popup.transient(self.root)
        self.generating_popup.grab_set()
        ctk.CTkLabel(self.generating_popup, text="🔄 Generating voice...", font=("Segoe UI", 14)).pack(expand=True)

    def close_generating_popup(self):
        if hasattr(self, 'generating_popup') and self.generating_popup:
            self.generating_popup.grab_release()
            self.generating_popup.destroy()
            self.generating_popup = None

    def run_speak_async(self, text, voice):
        async def run():
            self.root.after(0, self.show_generating_popup)

            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init()

                chunks = chunk_text(text)
                for chunk in chunks:
                    if self.stop_requested:
                        break

                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                        mp3_path = tmp.name

                    rate = f"{self.speed.get() * 100 - 100:+.0f}%"
                    pitch = f"{int((self.pitch.get() - 1) * 50):+d}Hz"

                    communicate = edge_tts.Communicate(chunk, voice, rate=rate, pitch=pitch)
                    await communicate.save(mp3_path)

                    self.root.after(0, self.close_generating_popup)

                    pygame.mixer.music.load(mp3_path)
                    pygame.mixer.music.play()

                    while pygame.mixer.music.get_busy():
                        if self.stop_requested:
                            pygame.mixer.music.stop()
                            break
                        pygame.time.Clock().tick(10)

                    try:
                        os.remove(mp3_path)
                    except PermissionError:
                        time.sleep(0.5)
                        try:
                            os.remove(mp3_path)
                        except Exception:
                            pass

            except Exception as e:
                print("Error during speech generation:", e)

            finally:
                self.root.after(0, self.close_generating_popup)

        threading.Thread(target=lambda: asyncio.run(run()), daemon=True).start()

    def stop_audio(self):
        self.stop_requested = True
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()

    def save_mp3(self):
        text = self.text.get("1.0", "end-1c").strip()
        voice = self._current_short()
        if not text or not voice:
            return
        output_path = filedialog.asksaveasfilename(defaultextension=".mp3", filetypes=[("MP3", "*.mp3")])
        if output_path:
            threading.Thread(target=self.run_save_mp3,
                             args=(text, voice, self.speed.get(), self.pitch.get(), output_path), daemon=True).start()

    def run_save_mp3(self, text, voice, speed, pitch, output_path):
        async def run():
            try:
                chunks = chunk_text(text, max_len=3000)
                with open(output_path, "wb") as out_file:
                    for chunk in chunks:
                        rate = f"{speed * 100 - 100:+.0f}%"
                        pitch_str = f"{(pitch - 1) * 50:+.0f}Hz"
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                            tmp_path = tmp.name

                        communicate = edge_tts.Communicate(chunk, voice, rate=rate, pitch=pitch_str)
                        await communicate.save(tmp_path)

                        with open(tmp_path, "rb") as f:
                            out_file.write(f.read())

                        os.remove(tmp_path)

                save_recent_export(output_path)
                messagebox.showinfo("Success", f"Saved to {output_path}")

            except Exception as e:
                messagebox.showerror("Error", f"Failed to save MP3:\n{e}")

        threading.Thread(target=lambda: asyncio.run(run()), daemon=True).start()

    def back_to_home(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        StartPage(self.root, self.voices)


class MultiVoiceApp:
    def __init__(self, root, voices):
        self.root = root
        self.voices = voices
        self.favorites = load_favorites()
        self.stop_requested = False
        self.voice_use_rows = []  # list of (StringVar, frame) for the "Voices to Use" box
        self.current_voice_index = 0
        self.all_display_names, self.display_to_short, self.short_to_display = build_voice_maps(voices)
        self.all_voice_names = self.all_display_names

        for widget in root.winfo_children():
            widget.destroy()

        main_container = ctk.CTkFrame(root)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)

        # Top Split Area — fixed height so both panels stay inside their own space
        top_frame = ctk.CTkFrame(main_container, height=230)
        top_frame.pack(fill="x", padx=10, pady=(10, 5))
        top_frame.pack_propagate(False)
        top_frame.grid_rowconfigure(0, weight=1)

        # --- Left: Name-Based Split Panel ---
        name_split_frame = ctk.CTkFrame(top_frame)
        name_split_frame.grid(row=0, column=0, sticky="nsew", padx=(5, 5), pady=5)
        top_frame.grid_columnconfigure(0, weight=3)

        ctk.CTkLabel(name_split_frame, text="🎙️ Name-Based Split", font=("Segoe UI", 12, "bold")).pack(anchor="w",
                                                                                                       padx=10,
                                                                                                       pady=(5, 0))
        self.text_input = ctk.CTkTextbox(name_split_frame, font=("Segoe UI", 11))
        self.text_input.pack(fill="both", expand=True, padx=10, pady=5)

        options_frame = ctk.CTkFrame(name_split_frame, fg_color="transparent")
        options_frame.pack(fill="x", padx=10, pady=(0, 8))

        self.remove_names_var = ctk.BooleanVar(value=True)
        chk = ctk.CTkCheckBox(options_frame, text="Remove Names (e.g., John:)", variable=self.remove_names_var)
        chk.pack(side="left")

        btn_split = ctk.CTkButton(options_frame, text="👥 Name-Based Auto Split", command=self.name_based_split)
        btn_split.pack(side="right")

        # --- Right: Voices to Use Box ---
        voice_box_frame = ctk.CTkFrame(top_frame)
        voice_box_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 5), pady=5)
        top_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(voice_box_frame, text="🎤 Voices to Use", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10,
                                                                                                  pady=(5, 0))

        self.selected_voices_frame = ctk.CTkScrollableFrame(voice_box_frame)
        self.selected_voices_frame.pack(fill="both", expand=True, padx=5, pady=5)

        fav_row = ctk.CTkFrame(voice_box_frame, fg_color="transparent")
        fav_row.pack(fill="x", padx=10, pady=(0, 5))

        fav_display_names = [self.short_to_display[s] for s in self.favorites if s in self.short_to_display]
        self.fav_quick_var = ctk.StringVar(value=fav_display_names[0] if fav_display_names else "")
        self.fav_quick_dropdown = ctk.CTkOptionMenu(
            fav_row, variable=self.fav_quick_var,
            values=fav_display_names if fav_display_names else ["No favorites yet"], width=140
        )
        self.fav_quick_dropdown.pack(side="left", fill="x", expand=True, padx=(0, 5))

        ctk.CTkButton(fav_row, text="⭐ Add", width=70, command=self.add_favorite_to_use_box).pack(side="left")

        btn_add_voice = ctk.CTkButton(voice_box_frame, text="➕ Add Voice", command=self.add_voice_to_use_box)
        btn_add_voice.pack(anchor="e", padx=10, pady=(0, 5))

        # Voices to Use starts blank — favorites are added manually via the ⭐ Add button

        # --- Scrollable Row Content Area ---
        self.inner_frame = ctk.CTkScrollableFrame(main_container)
        self.inner_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Global Control Buttons
        btns = ctk.CTkFrame(main_container)
        btns.pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(btns, text="➕ Add Sentence", command=self.add_sentence).grid(row=0, column=0, padx=6, pady=5)
        ctk.CTkButton(btns, text="🗑 Remove Sentence", command=self.remove_sentence).grid(row=0, column=1, padx=6,
                                                                                         pady=5)
        ctk.CTkButton(btns, text="🔊 Speak All", command=self.speak_all).grid(row=0, column=2, padx=6, pady=5)
        ctk.CTkButton(btns, text="💾 Save All", command=self.save_all).grid(row=0, column=3, padx=6, pady=5)
        ctk.CTkButton(btns, text="⏹ Stop All", fg_color="transparent", border_width=1, command=self.stop_audio).grid(
            row=0, column=4, padx=6, pady=5)

        ctk.CTkButton(main_container, text="🔙 Back to Home", fg_color="transparent", border_width=1,
                      command=self.back_to_home).pack(pady=(0, 5))

        self.voice_rows = []

        self.add_sentence()

    def add_voice_to_use_box(self, preset_short=None):
        var = ctk.StringVar()
        if preset_short and preset_short in self.short_to_display:
            var.set(self.short_to_display[preset_short])
        elif self.all_voice_names:
            var.set(self.all_voice_names[0])

        voice_frame = ctk.CTkFrame(self.selected_voices_frame)
        voice_frame.pack(fill="x", pady=2)

        voice_menu = ctk.CTkOptionMenu(voice_frame, variable=var, values=self.all_voice_names)
        voice_menu.pack(side="left", padx=5, fill="x", expand=True)

        ctk.CTkButton(voice_frame, text="⬆️", width=28,
                      command=lambda f=voice_frame: self.move_voice_use_row_up(f)).pack(side="left", padx=1)
        ctk.CTkButton(voice_frame, text="⬇️", width=28,
                      command=lambda f=voice_frame: self.move_voice_use_row_down(f)).pack(side="left", padx=1)

        remove_btn = ctk.CTkButton(
            voice_frame,
            text="❌",
            width=30,
            command=lambda: self.remove_voice_from_box(voice_frame)
        )
        remove_btn.pack(side="right", padx=5)

        self.voice_use_rows.append((var, voice_frame))

    def add_favorite_to_use_box(self):
        display = self.fav_quick_var.get()
        if not display or display not in self.display_to_short:
            return
        self.add_voice_to_use_box(preset_short=self.display_to_short[display])

    def remove_voice_from_box(self, frame):
        self.voice_use_rows = [(v, f) for v, f in self.voice_use_rows if f != frame]
        frame.destroy()

    def _refresh_voice_use_rows(self):
        for _, frame in self.voice_use_rows:
            frame.pack_forget()
        for _, frame in self.voice_use_rows:
            frame.pack(fill="x", pady=2)

    def move_voice_use_row_up(self, frame):
        index = next((i for i, (_, f) in enumerate(self.voice_use_rows) if f == frame), None)
        if index is not None and index > 0:
            self.voice_use_rows[index], self.voice_use_rows[index - 1] = \
                self.voice_use_rows[index - 1], self.voice_use_rows[index]
            self._refresh_voice_use_rows()

    def move_voice_use_row_down(self, frame):
        index = next((i for i, (_, f) in enumerate(self.voice_use_rows) if f == frame), None)
        if index is not None and index < len(self.voice_use_rows) - 1:
            self.voice_use_rows[index], self.voice_use_rows[index + 1] = \
                self.voice_use_rows[index + 1], self.voice_use_rows[index]
            self._refresh_voice_use_rows()

    def name_based_split(self):
        text = self.text_input.get("1.0", "end-1c")
        if not text.strip():
            messagebox.showwarning("Empty Input", "Please enter text to split.")
            return

        voices_list = [v.get() for v, _ in self.voice_use_rows if v.get()]
        if not voices_list:
            messagebox.showwarning("No Voices Selected", "Please add at least one voice in the Voices-to-Use box.")
            return

        remove_names = self.remove_names_var.get()
        segments = []          # (speaker_name, text_to_speak)
        current_name = None
        current_lines = []

        def flush():
            if current_name is not None and current_lines:
                combined = " ".join(current_lines).strip()
                if combined:
                    text_to_add = combined if remove_names else f"{current_name}: {combined}"
                    segments.append((current_name, text_to_add))

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            # Only treat "Name:" as a new speaker when it matches a real name pattern
            # (short, alphabetic) — avoids false splits on things like "10:30" or a
            # sentence that just happens to contain a colon.
            match = SPEAKER_LINE_RE.match(line)
            if match:
                flush()
                current_name = match.group(1).strip()
                rest = match.group(2).strip()
                current_lines = [rest] if rest else []
            else:
                if current_name is None:
                    current_name = "Narrator"
                current_lines.append(line)

        flush()

        if not segments:
            messagebox.showinfo("No Names Found", "No name-based lines were found.")
            return

        # Assign each unique speaker a voice, round-robin across the Voices-to-Use list
        unique_names = []
        for name, _ in segments:
            if name not in unique_names:
                unique_names.append(name)
        name_to_voice = {name: voices_list[i % len(voices_list)] for i, name in enumerate(unique_names)}

        for row in self.voice_rows[:]:
            self.remove_row(row[4])

        for name, sentence in segments:
            self.add_sentence(preload_text=sentence)
            t, v, s, p, _ = self.voice_rows[-1]
            v.set(name_to_voice[name])

    def add_sentence(self, preload_text=""):
        row_frame = ctk.CTkFrame(self.inner_frame)
        row_frame.pack(fill="x", pady=5, padx=5)
        row_frame.grid_columnconfigure(0, weight=1)

        txt = ctk.CTkTextbox(row_frame, height=65, font=("Segoe UI", 11))
        txt.grid(row=0, column=0, rowspan=3, sticky="nsew", padx=(5, 10), pady=5)

        if preload_text:
            txt.insert("1.0", preload_text)

        voice_var = ctk.StringVar()
        voice_combo = ctk.CTkOptionMenu(row_frame, variable=voice_var, values=self.all_voice_names, width=200)

        voices_list = [v.get() for v, _ in self.voice_use_rows if v.get()]
        if not voices_list:
            voices_list = [self.all_voice_names[0]] if self.all_voice_names else [""]

        if self.current_voice_index >= len(voices_list):
            self.current_voice_index = 0

        voice_to_use = voices_list[self.current_voice_index]
        voice_var.set(voice_to_use)
        self.current_voice_index = (self.current_voice_index + 1) % len(voices_list)

        voice_combo.grid(row=0, column=1, columnspan=4, sticky="w", padx=5, pady=2)

        # Speed
        s_var = tk.DoubleVar(value=1.0)
        ctk.CTkLabel(row_frame, text="Speed:", font=("Segoe UI", 10)).grid(row=1, column=1, sticky="w", padx=2)
        speed_slider = ctk.CTkSlider(row_frame, from_=0.5, to=2.0, variable=s_var, width=90)
        speed_slider.grid(row=1, column=2, sticky="w", padx=2)
        speed_label = ctk.CTkLabel(row_frame, text=f"{s_var.get():.2f}", width=30, font=("Segoe UI", 10))
        speed_label.grid(row=1, column=3, padx=2)
        ctk.CTkButton(row_frame, text="Reset", width=35, font=("Segoe UI", 9),
                      command=lambda sv=s_var: sv.set(1.0)).grid(row=1, column=4, padx=2)
        s_var.trace_add("write", lambda *args, sv=s_var, lbl=speed_label: lbl.configure(text=f"{sv.get():.2f}"))

        # Pitch
        p_var = tk.DoubleVar(value=1.0)
        ctk.CTkLabel(row_frame, text="Pitch:", font=("Segoe UI", 10)).grid(row=2, column=1, sticky="w", padx=2)
        pitch_slider = ctk.CTkSlider(row_frame, from_=0.5, to=2.0, variable=p_var, width=90)
        pitch_slider.grid(row=2, column=2, sticky="w", padx=2)
        pitch_label = ctk.CTkLabel(row_frame, text=f"{p_var.get():.2f}", width=30, font=("Segoe UI", 10))
        pitch_label.grid(row=2, column=3, padx=2)
        ctk.CTkButton(row_frame, text="Reset", width=35, font=("Segoe UI", 9),
                      command=lambda pv=p_var: pv.set(1.0)).grid(row=2, column=4, padx=2)
        p_var.trace_add("write", lambda *args, pv=p_var, lbl=pitch_label: lbl.configure(text=f"{pv.get():.2f}"))

        # Action Buttons (Play / Stop / Move / Clone / Remove)
        btn_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        btn_frame.grid(row=0, column=5, rowspan=3, sticky="ns", padx=5)

        ctk.CTkButton(
            btn_frame, text="🔊", width=30,
            command=lambda t=txt, v=voice_var, s=s_var, p=p_var: self.speak_single_row(t, v, s, p)
        ).grid(row=0, column=0, padx=1, pady=1)

        ctk.CTkButton(
            btn_frame, text="⏹", width=30, fg_color="transparent", border_width=1,
            command=self.stop_audio
        ).grid(row=0, column=1, padx=1, pady=1)

        ctk.CTkButton(btn_frame, text="⬆️", width=30, command=lambda f=row_frame: self.move_row_up(f)).grid(row=1,
                                                                                                            column=0,
                                                                                                            padx=1,
                                                                                                            pady=1)
        ctk.CTkButton(btn_frame, text="⬇️", width=30, command=lambda f=row_frame: self.move_row_down(f)).grid(row=1,
                                                                                                              column=1,
                                                                                                              padx=1,
                                                                                                              pady=1)

        ctk.CTkButton(
            btn_frame, text="📥", width=30,
            command=lambda t=txt, v=voice_var, s=s_var, p=p_var, f=row_frame: self.clone_row(t, v, s, p, f)
        ).grid(row=2, column=0, padx=1, pady=1)

        ctk.CTkButton(btn_frame, text="❌", width=30, command=lambda f=row_frame: self.remove_row(f)).grid(row=2,
                                                                                                          column=1,
                                                                                                          padx=1,
                                                                                                          pady=1)

        self.voice_rows.append((txt, voice_var, s_var, p_var, row_frame))

    def speak_single_row(self, txt_widget, voice_var, speed_var, pitch_var):
        text = txt_widget.get("1.0", "end-1c").strip()
        voice = self.display_to_short.get(voice_var.get(), voice_var.get())
        if not text or not voice:
            return
        self.stop_requested = False
        sentences = [(text, voice, speed_var.get(), pitch_var.get())]
        threading.Thread(target=self.run_multi_speak, args=(sentences,), daemon=True).start()

    def remove_sentence(self):
        if self.voice_rows:
            t, v, s, p, frame = self.voice_rows.pop()
            frame.destroy()

    def remove_row(self, frame):
        for i, (_, _, _, _, row_frame) in enumerate(self.voice_rows):
            if row_frame == frame:
                self.voice_rows.pop(i)
                row_frame.destroy()
                break

    def move_row_up(self, frame):
        index = next((i for i, (_, _, _, _, r) in enumerate(self.voice_rows) if r == frame), None)
        if index is not None and index > 0:
            self.voice_rows[index], self.voice_rows[index - 1] = self.voice_rows[index - 1], self.voice_rows[index]
            self.refresh_rows()

    def move_row_down(self, frame):
        index = next((i for i, (_, _, _, _, r) in enumerate(self.voice_rows) if r == frame), None)
        if index is not None and index < len(self.voice_rows) - 1:
            self.voice_rows[index], self.voice_rows[index + 1] = self.voice_rows[index + 1], self.voice_rows[index]
            self.refresh_rows()

    def refresh_rows(self):
        for _, _, _, _, frame in self.voice_rows:
            frame.pack_forget()
        for _, _, _, _, frame in self.voice_rows:
            frame.pack(fill="x", pady=5, padx=5)

    def clone_row(self, t_orig, v_orig, s_orig, p_orig, insert_after_frame):
        index = next((i for i, (_, _, _, _, f) in enumerate(self.voice_rows) if f == insert_after_frame),
                     len(self.voice_rows) - 1)
        self.add_sentence()
        new_row = self.voice_rows.pop()
        self.voice_rows.insert(index + 1, new_row)

        t, v, s, p, _ = new_row
        t.delete("1.0", "end")
        t.insert("1.0", t_orig.get("1.0", "end-1c"))
        v.set(v_orig.get())
        s.set(s_orig.get())
        p.set(p_orig.get())
        self.refresh_rows()

    def speak_all(self):
        self.stop_requested = False
        sentences = [
            (t.get("1.0", "end-1c").strip(), self.display_to_short.get(v.get(), v.get()), s.get(), p.get())
            for t, v, s, p, _ in self.voice_rows
            if t.get("1.0", "end-1c").strip()
        ]
        threading.Thread(target=self.run_multi_speak, args=(sentences,), daemon=True).start()

    def run_multi_speak(self, sentences):
        def run_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._run_multi_speak_async(sentences))
            loop.close()

        threading.Thread(target=run_in_thread, daemon=True).start()

    async def _run_multi_speak_async(self, sentences):
        self.root.after(0, self.show_generating_popup)

        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()

            for i, (text, voice, speed, pitch) in enumerate(sentences):
                if self.stop_requested:
                    break

                rate = f"{speed * 100 - 100:+.0f}%"
                pitch_str = f"{int((pitch - 1) * 50):+d}Hz"

                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                    mp3_path = tmp.name

                communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch_str)
                await communicate.save(mp3_path)

                if i == 0:
                    self.root.after(0, self.close_generating_popup)

                pygame.mixer.music.load(mp3_path)
                pygame.mixer.music.play()

                while pygame.mixer.music.get_busy():
                    if self.stop_requested:
                        pygame.mixer.music.stop()
                        break
                    pygame.time.Clock().tick(10)

                try:
                    os.remove(mp3_path)
                except Exception:
                    time.sleep(0.5)
                    try:
                        os.remove(mp3_path)
                    except Exception:
                        pass

        except Exception as e:
            print("Multi speak error:", e)

        finally:
            self.root.after(0, self.close_generating_popup)

    def save_all(self):
        output_path = filedialog.asksaveasfilename(defaultextension=".mp3", filetypes=[("MP3 files", "*.mp3")])
        if not output_path:
            return
        all_data = [
            (t.get("1.0", "end-1c").strip(), self.display_to_short.get(v.get(), v.get()), s.get(), p.get())
            for t, v, s, p, _ in self.voice_rows
            if t.get("1.0", "end-1c").strip() and v.get()
        ]
        threading.Thread(target=self.run_save_all, args=(all_data, output_path), daemon=True).start()

    def run_save_all(self, data, output_path):
        async def run():
            try:
                self.root.after(0, lambda: self.show_progress_popup(len(data)))
                with open(output_path, "wb") as out_file:
                    for i, (text, voice, speed, pitch) in enumerate(data):
                        rate = f"{speed * 100 - 100:+.0f}%"
                        pitch_str = f"{(pitch - 1) * 50:+.0f}Hz"
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                            tmp_path = tmp.name

                        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch_str)
                        await communicate.save(tmp_path)

                        with open(tmp_path, "rb") as f:
                            out_file.write(f.read())

                        os.remove(tmp_path)
                        self.root.after(0, lambda val=i + 1: self.update_progress(val, len(data)))

                save_recent_export(output_path)
                self.root.after(0, lambda: messagebox.showinfo("Success", f"Audio saved to {output_path}"))

            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                self.root.after(0, self.close_progress_popup)

        threading.Thread(target=lambda: asyncio.run(run()), daemon=True).start()

    def stop_audio(self):
        self.stop_requested = True
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()

    def back_to_home(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        StartPage(self.root, self.voices)

    def show_generating_popup(self):
        self.generating_popup = ctk.CTkToplevel(self.root)
        self.generating_popup.title("Please wait")
        self.generating_popup.geometry("300x120")
        self.generating_popup.resizable(False, False)
        self.generating_popup.transient(self.root)
        self.generating_popup.grab_set()
        ctk.CTkLabel(self.generating_popup, text="🔄 Generating voice...", font=("Segoe UI", 14)).pack(expand=True)

    def close_generating_popup(self):
        if hasattr(self, 'generating_popup') and self.generating_popup:
            self.generating_popup.grab_release()
            self.generating_popup.destroy()
            self.generating_popup = None

    def show_progress_popup(self, total):
        self.progress_popup = ctk.CTkToplevel(self.root)
        self.progress_popup.title("Saving Audio")
        self.progress_popup.geometry("350x120")
        self.progress_popup.resizable(False, False)
        self.progress_popup.transient(self.root)
        self.progress_popup.grab_set()

        ctk.CTkLabel(self.progress_popup, text="Saving audio, please wait...", font=("Segoe UI", 12)).pack(pady=(15, 5))

        self.progress_bar = ctk.CTkProgressBar(self.progress_popup, width=300)
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=5)

        self.percent_label = ctk.CTkLabel(self.progress_popup, text="0%", font=("Segoe UI", 11))
        self.percent_label.pack()

    def update_progress(self, value, total):
        progress = value / total
        self.progress_bar.set(progress)
        self.percent_label.configure(text=f"{int(progress * 100)}%")

    def close_progress_popup(self):
        if hasattr(self, 'progress_popup') and self.progress_popup:
            self.progress_popup.grab_release()
            self.progress_popup.destroy()
            self.progress_popup = None

# --- App Bootstrap ---

class LoadingScreen:
    """Shown briefly while the voice list is fetched from Microsoft Edge TTS."""

    def __init__(self, root, on_ready):
        self.root = root
        self.on_ready = on_ready

        self.frame = ctk.CTkFrame(root, fg_color="transparent")
        self.frame.pack(expand=True, fill="both")

        ctk.CTkLabel(self.frame, text="🎙", font=("Segoe UI", 48)).pack(expand=True, pady=(0, 10))
        ctk.CTkLabel(self.frame, text="AI Voice Generator", font=("Segoe UI", 20, "bold")).pack()
        self.status = ctk.CTkLabel(self.frame, text="Loading available voices…",
                                    font=("Segoe UI", 12), text_color=("gray30", "gray70"))
        self.status.pack(pady=(5, 15))
        self.spinner = ctk.CTkProgressBar(self.frame, width=260, mode="indeterminate")
        self.spinner.pack()
        self.spinner.start()

        threading.Thread(target=self.fetch_voices, daemon=True).start()

    def fetch_voices(self):
        try:
            voices = asyncio.run(edge_tts.list_voices())
            voices = sorted(voices, key=lambda v: v["ShortName"])
        except Exception as e:
            self.root.after(0, lambda: self.show_error(str(e)))
            return
        self.root.after(0, lambda: self.finish(voices))

    def show_error(self, message):
        self.spinner.stop()
        self.status.configure(text=f"Failed to load voices:\n{message}", text_color="red")
        ctk.CTkButton(self.frame, text="🔁 Retry", command=self.retry).pack(pady=15)

    def retry(self):
        self.frame.destroy()
        LoadingScreen(self.root, self.on_ready)

    def finish(self, voices):
        self.spinner.stop()
        self.frame.destroy()
        self.on_ready(voices)


class VoiceGeneratorApp:
    """Top-level application: window chrome, lifecycle, and page routing."""

    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("AI Voice Generator")
        self.root.geometry("1000x720")
        self.root.minsize(820, 600)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Center the window on screen
        self.root.update_idletasks()
        w, h = 1000, 720
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        LoadingScreen(self.root, self.launch_home)

    def launch_home(self, voices):
        if not voices:
            messagebox.showerror("No Voices", "No voices were returned by the service.")
            self.root.destroy()
            return
        StartPage(self.root, voices)

    def on_close(self):
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.quit()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    VoiceGeneratorApp().run()
