import threading
import tkinter as tk
from tkinter import ttk, messagebox

import atak_downloader_finalbuild as downloader
import atak_imagery_sqlite_builder_finalbuild as sqlite_builder
import atak_dted_downloader as dted

APP_TITLE = "ATAK Pipeline"

class App:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("500x220")

        self.status = tk.StringVar(value="Ready")
        self.progress = tk.IntVar(value=0)

        frame = tk.Frame(root, padx=20, pady=20)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text=APP_TITLE, font=("Arial", 14, "bold")).pack(anchor="w")
        tk.Label(frame, textvariable=self.status).pack(anchor="w", pady=(10,10))

        self.bar = ttk.Progressbar(frame, length=400, maximum=100)
        self.bar.pack(anchor="w", pady=(0,10))

        self.btn = tk.Button(frame, text="Start Pipeline", command=self.start)
        self.btn.pack(anchor="w")

    def start(self):
        self.btn.config(state="disabled")
        threading.Thread(target=self.run, daemon=True).start()

    def set(self, text, pct):
        def update():
            self.status.set(text)
            self.bar["value"] = pct
        self.root.after(0, update)

    def run(self):
        try:
            self.set("Running Imagery Downloader", 0)
            downloader.main()

            self.set("Running SQLite Builder", 33)
            sqlite_builder.main()

            self.set("Running DTED Downloader", 66)
            dted.main()

            self.set("Complete", 100)
            messagebox.showinfo(APP_TITLE, "Pipeline complete")
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))

root = tk.Tk()
App(root)
root.mainloop()
