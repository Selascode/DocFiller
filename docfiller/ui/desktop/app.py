"""Fenêtre principale de DocFiller (desktop, CustomTkinter).

L'interface ne contient aucune logique métier : elle délègue tout
à `DocumentProcessor` (docfiller.core), réutilisable sur mobile.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from docfiller.config import APP_NAME, SETTINGS_FILENAME, default_data_dir
from docfiller.core import (
    Analysis,
    DataStore,
    DocFillerError,
    DocumentProcessor,
    ProcessingCancelled,
)
from docfiller.core.report import format_fields_summary, format_report
from docfiller.ui.desktop.dialogs import DialogAction, MissingFieldDialog

try:  # Le glisser-déposer est optionnel : l'application reste utilisable sans.
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _DND_IMPORTED = True
except ImportError:  # pragma: no cover - dépend de l'installation
    _DND_IMPORTED = False

logger = logging.getLogger(__name__)

_OUTPUT_DIR_SETTING = "dossier_sortie"
_MUTED_COLOR = ("gray40", "gray65")
_SUCCESS_COLOR = ("#1e8449", "#58d68d")
_ERROR_COLOR = ("#c0392b", "#ff6b6b")
_DROP_BORDER = ("gray70", "gray35")
_DROP_BORDER_ACTIVE = ("#3B8ED0", "#1F6AA5")

_BaseWindow: type = ctk.CTk
if _DND_IMPORTED:
    class _DnDWindow(ctk.CTk, TkinterDnD.DnDWrapper):
        """Fenêtre CustomTkinter compatible tkinterdnd2."""

    _BaseWindow = _DnDWindow


class DocFillerApp(_BaseWindow):  # type: ignore[misc, valid-type]
    """Fenêtre principale : dépôt du PDF, dossier de sortie, traitement."""

    def __init__(self, processor: DocumentProcessor, settings: DataStore) -> None:
        super().__init__()
        self.processor = processor
        self.settings = settings
        self._pdf_path: Path | None = None
        self._last_output: Path | None = None
        self._dnd_enabled = self._init_dnd()

        self.title(APP_NAME)
        self.geometry("680x620")
        self.minsize(520, 520)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        self._build_header()
        self._build_drop_zone()
        self._build_output_selector()
        self._build_actions()
        self._build_report()

    # ------------------------------------------------------------------ #
    # Initialisation
    # ------------------------------------------------------------------ #
    def _init_dnd(self) -> bool:
        """Charge l'extension Tk « tkdnd ». Retourne False si indisponible."""
        if not _DND_IMPORTED:
            return False
        try:
            self.TkdndVersion = TkinterDnD._require(self)
            return True
        except (RuntimeError, tk.TclError) as exc:
            logger.warning("Glisser-déposer indisponible : %s", exc)
            return False

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 8))
        ctk.CTkLabel(header, text=APP_NAME, font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="Remplissage automatique de formulaires PDF à partir de vos données.",
            text_color=_MUTED_COLOR,
        ).pack(anchor="w")

    def _build_drop_zone(self) -> None:
        self._drop_zone = ctk.CTkFrame(self, height=150, corner_radius=14, border_width=2, border_color=_DROP_BORDER)
        self._drop_zone.grid(row=1, column=0, sticky="ew", padx=24, pady=8)
        self._drop_zone.grid_propagate(False)
        self._drop_zone.grid_columnconfigure(0, weight=1)
        self._drop_zone.grid_rowconfigure((0, 3), weight=1)

        hint = "Glissez-déposez un formulaire PDF ici" if self._dnd_enabled else "Aucun formulaire sélectionné"
        self._drop_title = ctk.CTkLabel(self._drop_zone, text=hint, font=ctk.CTkFont(size=16, weight="bold"))
        self._drop_title.grid(row=1, column=0, padx=16)
        sub = "ou cliquez pour parcourir vos fichiers" if self._dnd_enabled else "Cliquez ici pour choisir un PDF"
        self._drop_subtitle = ctk.CTkLabel(self._drop_zone, text=sub, text_color=_MUTED_COLOR, wraplength=560)
        self._drop_subtitle.grid(row=2, column=0, padx=16)

        for widget in self._walk(self._drop_zone):
            widget.bind("<Button-1>", lambda _e: self._browse_pdf(), add="+")
            widget.configure(cursor="hand2")
            if self._dnd_enabled:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<DropEnter>>", self._on_drag_enter)
                widget.dnd_bind("<<DropLeave>>", self._on_drag_leave)
                widget.dnd_bind("<<Drop>>", self._on_drop)

    def _build_output_selector(self) -> None:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=2, column=0, sticky="ew", padx=24, pady=8)
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text="Dossier de destination", anchor="w").grid(row=0, column=0, columnspan=2, sticky="ew")

        self._output_var = ctk.StringVar(value=self.settings.get(_OUTPUT_DIR_SETTING) or "")
        self._output_entry = ctk.CTkEntry(
            frame, textvariable=self._output_var, placeholder_text="Même dossier que le PDF d'origine"
        )
        self._output_entry.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        ctk.CTkButton(frame, text="Parcourir…", width=110, command=self._browse_output_dir).grid(
            row=1, column=1, padx=(8, 0), pady=(4, 0)
        )

    def _build_actions(self) -> None:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=3, column=0, sticky="ew", padx=24, pady=(12, 8))
        frame.grid_columnconfigure(0, weight=1)
        self._process_button = ctk.CTkButton(
            frame,
            text="Traiter le document",
            height=42,
            font=ctk.CTkFont(size=15, weight="bold"),
            state="disabled",
            command=self._process,
        )
        self._process_button.grid(row=0, column=0, sticky="ew")
        self._status_label = ctk.CTkLabel(frame, text="", anchor="w", wraplength=620, justify="left")
        self._status_label.grid(row=1, column=0, sticky="ew", pady=(6, 0))

    def _build_report(self) -> None:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=4, column=0, sticky="nsew", padx=24, pady=(0, 20))
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        self._report = ctk.CTkTextbox(frame, wrap="word", state="disabled", font=ctk.CTkFont(size=12))
        self._report.grid(row=0, column=0, columnspan=3, sticky="nsew")

        self._open_pdf_button = ctk.CTkButton(
            frame, text="Ouvrir le PDF généré", state="disabled", command=lambda: self._open(self._last_output)
        )
        self._open_pdf_button.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self._open_dir_button = ctk.CTkButton(
            frame,
            text="Ouvrir le dossier",
            state="disabled",
            fg_color="gray50",
            hover_color="gray40",
            command=lambda: self._open(self._last_output.parent if self._last_output else None),
        )
        self._open_dir_button.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(8, 0))
        ctk.CTkButton(
            frame,
            text="Mes données",
            fg_color="transparent",
            border_width=1,
            text_color=("gray10", "gray90"),
            width=110,
            command=lambda: self._open(self.processor.data_store.path),
        ).grid(row=1, column=2, sticky="e", pady=(8, 0))

    # ------------------------------------------------------------------ #
    # Sélection des fichiers
    # ------------------------------------------------------------------ #
    def _on_drag_enter(self, event: object) -> str:
        self._drop_zone.configure(border_color=_DROP_BORDER_ACTIVE)
        return getattr(event, "action", "copy")

    def _on_drag_leave(self, _event: object) -> None:
        self._drop_zone.configure(border_color=_DROP_BORDER)

    def _on_drop(self, event: object) -> str:
        self._on_drag_leave(event)
        # tkdnd fournit une liste Tcl : « {/chemin avec espaces/a.pdf} /autre.pdf ».
        paths = self.tk.splitlist(getattr(event, "data", ""))
        if paths:
            self.load_pdf(Path(paths[0]))
            if len(paths) > 1:
                self._set_status("Un seul document à la fois : seul le premier fichier a été pris en compte.")
        return getattr(event, "action", "copy")

    def _browse_pdf(self) -> None:
        initial_dir = str(self._pdf_path.parent) if self._pdf_path else str(Path.home())
        filename = filedialog.askopenfilename(
            parent=self,
            title="Choisir un formulaire PDF",
            initialdir=initial_dir,
            filetypes=[("Documents PDF", "*.pdf *.PDF"), ("Tous les fichiers", "*")],
        )
        if filename:
            self.load_pdf(Path(filename))

    def _browse_output_dir(self) -> None:
        initial = self._output_var.get() or (str(self._pdf_path.parent) if self._pdf_path else str(Path.home()))
        directory = filedialog.askdirectory(parent=self, title="Dossier de destination", initialdir=initial)
        if directory:
            self._output_var.set(directory)

    def load_pdf(self, path: Path) -> None:
        """Charge un PDF et affiche un aperçu de l'analyse."""
        if path.suffix.lower() != ".pdf":
            self._show_error("Format non pris en charge", f"« {path.name} » n'est pas un fichier PDF.")
            return
        try:
            analysis = self.processor.analyze(path)
        except DocFillerError as exc:
            self._pdf_path = None
            self._process_button.configure(state="disabled")
            self._drop_title.configure(text=path.name)
            self._drop_subtitle.configure(text="Cliquez pour choisir un autre fichier")
            self._set_status(str(exc), error=True)
            return

        self._pdf_path = path
        self._drop_title.configure(text=path.name)
        self._drop_subtitle.configure(text=format_fields_summary(analysis))
        self._process_button.configure(state="normal")
        self._set_status("Prêt. Cliquez sur « Traiter le document ».")

    # ------------------------------------------------------------------ #
    # Traitement
    # ------------------------------------------------------------------ #
    def _resolve_output_dir(self) -> Path | None:
        assert self._pdf_path is not None
        raw = self._output_var.get().strip()
        directory = Path(raw).expanduser() if raw else self._pdf_path.parent
        if not directory.is_dir():
            create = messagebox.askyesno(
                "Dossier introuvable", f"Le dossier « {directory} » n'existe pas.\nVoulez-vous le créer ?", parent=self
            )
            if not create:
                return None
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                self._show_error("Dossier invalide", f"Impossible de créer le dossier :\n{exc}")
                return None
        if not os.access(directory, os.W_OK):
            self._show_error("Dossier en lecture seule", f"Impossible d'écrire dans « {directory} ».")
            return None
        return directory

    def _process(self) -> None:
        if self._pdf_path is None:
            return
        output_dir = self._resolve_output_dir()
        if output_dir is None:
            return

        self._set_busy(True)
        try:
            analysis = self.processor.analyze(self._pdf_path)
            self._ask_missing_fields(analysis)
            self._set_status("Génération du document…")
            result = self.processor.generate(analysis, output_dir)
        except ProcessingCancelled:
            self._set_status("Traitement annulé. Aucun fichier n'a été créé.")
            return
        except DocFillerError as exc:
            self._show_error("Erreur de traitement", str(exc))
            self._set_status(str(exc), error=True)
            return
        except Exception as exc:  # Filet de sécurité : l'application ne doit pas planter
            logger.exception("Erreur inattendue")
            self._show_error("Erreur inattendue", f"{type(exc).__name__} : {exc}")
            return
        finally:
            self._set_busy(False)

        if self._output_var.get().strip():
            self.settings.set(_OUTPUT_DIR_SETTING, str(output_dir))
        self._last_output = result.output_path
        self._open_pdf_button.configure(state="normal")
        self._open_dir_button.configure(state="normal")
        self._set_report(format_report(analysis, result))
        message = f"Document généré : {result.output_path.name if result.output_path else ''}"
        if result.errors:
            message += f" ({len(result.errors)} champ(s) en erreur, voir le détail)"
        self._set_status(message, success=not result.errors, error=bool(result.errors))

    def _ask_missing_fields(self, analysis: Analysis) -> None:
        """Met le traitement en pause pour chaque champ inconnu (apprentissage actif).

        Raises:
            ProcessingCancelled: si l'utilisateur annule.
        """
        position = 0
        # La liste peut raccourcir : une réponse peut compléter d'autres champs.
        while analysis.pending:
            form_field = analysis.pending[0]
            position += 1
            total = position + len(analysis.pending) - 1
            self._set_status(f"Information manquante {position}/{total} : {form_field.display_label}")
            answer = MissingFieldDialog.ask(
                self,
                form_field,
                position,
                total,
                self.processor.suggest_key(form_field),
                self.processor.data_store.as_dict(),
            )
            if answer.action == DialogAction.CANCEL:
                raise ProcessingCancelled()
            if answer.action == DialogAction.SKIP_ALL:
                for remaining in analysis.pending:
                    self.processor.skip(analysis, remaining)
                return
            if answer.action == DialogAction.VALIDATE and answer.resolution is not None:
                self.processor.resolve(analysis, form_field, answer.resolution)
            else:
                self.processor.skip(analysis, form_field)

    # ------------------------------------------------------------------ #
    # Utilitaires d'affichage
    # ------------------------------------------------------------------ #
    def _set_busy(self, busy: bool) -> None:
        self._process_button.configure(state="disabled" if busy else "normal")
        self.configure(cursor="watch" if busy else "")
        self.update_idletasks()

    def _set_status(self, text: str, success: bool = False, error: bool = False) -> None:
        color = _ERROR_COLOR if error else _SUCCESS_COLOR if success else ("gray10", "gray90")
        self._status_label.configure(text=text, text_color=color)
        self.update_idletasks()

    def _set_report(self, text: str) -> None:
        self._report.configure(state="normal")
        self._report.delete("1.0", "end")
        self._report.insert("1.0", text)
        self._report.configure(state="disabled")

    def _show_error(self, title: str, message: str) -> None:
        messagebox.showerror(title, message, parent=self)

    def _open(self, path: Path | None) -> None:
        """Ouvre un fichier ou un dossier avec l'application par défaut du système."""
        if path is None or not path.exists():
            self._show_error("Introuvable", "Le fichier ou le dossier n'existe plus.")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            self._show_error("Ouverture impossible", str(exc))

    @staticmethod
    def _walk(widget: tk.Misc) -> list[tk.Misc]:
        """Le widget et tous ses descendants (pour le glisser-déposer et le clic)."""
        widgets = [widget]
        for child in widget.winfo_children():
            widgets.extend(DocFillerApp._walk(child))
        return widgets


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée de l'application desktop.

    Args:
        argv: arguments ; un chemin de PDF optionnel peut être fourni pour le précharger.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s : %(message)s")
    args = sys.argv[1:] if argv is None else argv

    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")

    data_dir = default_data_dir()
    try:
        processor = DocumentProcessor.from_directory(data_dir)
        settings = DataStore(data_dir / SETTINGS_FILENAME)
    except DocFillerError as exc:
        # Base illisible : on prévient sans rien écraser.
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(f"{APP_NAME} — données illisibles", f"{exc}\n\nCorrigez ou supprimez le fichier puis relancez.")
        root.destroy()
        return 1

    app = DocFillerApp(processor, settings)
    if args:
        app.after(100, lambda: app.load_pdf(Path(args[0])))
    app.mainloop()
    return 0
