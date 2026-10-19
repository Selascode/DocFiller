"""Boîte de dialogue « information manquante » (apprentissage actif)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

import customtkinter as ctk

from docfiller.core import FieldType, FormField, InvalidKeyError, Resolution, normalize_key

_NO_EXISTING = "—"
_SAVE_QUESTION = "Voulez-vous sauvegarder cette information pour les futurs documents ?"
_CHECKBOX_VALUES = ["Oui", "Non"]
_ERROR_COLOR = ("#c0392b", "#ff6b6b")
_MUTED_COLOR = ("gray40", "gray65")


class DialogAction(Enum):
    """Choix de l'utilisateur dans la boîte de dialogue."""

    VALIDATE = "valider"
    SKIP = "ignorer"
    SKIP_ALL = "ignorer_tout"
    CANCEL = "annuler"


@dataclass(frozen=True)
class DialogResult:
    action: DialogAction
    resolution: Resolution | None = None


class MissingFieldDialog(ctk.CTkToplevel):
    """Demande à l'utilisateur la valeur d'un champ non trouvé dans data.json.

    Utilisation : `result = MissingFieldDialog.ask(parent, champ, 1, 3, "cle", donnees)`.
    """

    def __init__(
        self,
        master: ctk.CTk,
        form_field: FormField,
        position: int,
        total: int,
        suggested_key: str,
        known_data: Mapping[str, str],
    ) -> None:
        super().__init__(master)
        self.result = DialogResult(DialogAction.SKIP)
        self._field = form_field
        self._known_data = dict(known_data)

        self.title(f"Information manquante ({position}/{total})")
        self.resizable(False, False)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", lambda: self._close(DialogAction.SKIP))
        self.bind("<Return>", lambda _e: self._validate())
        self.bind("<Escape>", lambda _e: self._close(DialogAction.SKIP))

        self._build(suggested_key)
        self._center_on(master)
        self._make_modal()

    @classmethod
    def ask(
        cls,
        master: ctk.CTk,
        form_field: FormField,
        position: int,
        total: int,
        suggested_key: str,
        known_data: Mapping[str, str],
    ) -> DialogResult:
        """Affiche la boîte de dialogue et attend la réponse (bloquant)."""
        dialog = cls(master, form_field, position, total, suggested_key, known_data)
        master.wait_window(dialog)
        return dialog.result

    # ------------------------------------------------------------------ #
    # Construction de l'interface
    # ------------------------------------------------------------------ #
    def _build(self, suggested_key: str) -> None:
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=16)
        body.grid_columnconfigure(0, weight=1)
        row = 0

        ctk.CTkLabel(
            body, text="Ce champ n'a pas été trouvé dans vos données :", text_color=_MUTED_COLOR, anchor="w"
        ).grid(row=row, column=0, sticky="ew")
        row += 1
        ctk.CTkLabel(
            body,
            text=self._field.display_label,
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
            justify="left",
            wraplength=440,
        ).grid(row=row, column=0, sticky="ew", pady=(2, 0))
        row += 1
        details = f"{self._field.field_type.value.capitalize()} · page {self._field.page + 1} · champ « {self._field.name} »"
        ctk.CTkLabel(
            body, text=details, text_color=_MUTED_COLOR, font=ctk.CTkFont(size=11), anchor="w", wraplength=440
        ).grid(row=row, column=0, sticky="ew", pady=(0, 12))
        row += 1

        # Saisie de la valeur, adaptée au type de champ.
        ctk.CTkLabel(body, text="Valeur :", anchor="w").grid(row=row, column=0, sticky="ew")
        row += 1
        self._value_widget = self._build_value_widget(body)
        self._value_widget.grid(row=row, column=0, sticky="ew", pady=(2, 10))
        row += 1

        # Réutilisation d'une donnée existante (apprend une correspondance).
        if self._known_data:
            ctk.CTkLabel(body, text="Ou réutiliser une donnée existante :", anchor="w").grid(
                row=row, column=0, sticky="ew"
            )
            row += 1
            choices = [_NO_EXISTING, *(f"{key} : {value}" for key, value in sorted(self._known_data.items()))]
            self._existing = ctk.CTkOptionMenu(body, values=choices, command=self._on_existing_selected)
            self._existing.set(_NO_EXISTING)
            self._existing.grid(row=row, column=0, sticky="ew", pady=(2, 10))
            row += 1

        # Sauvegarde pour les futurs documents.
        self._save_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            body, text=_SAVE_QUESTION, variable=self._save_var, command=self._on_save_toggled
        ).grid(row=row, column=0, sticky="w", pady=(4, 6))
        row += 1

        key_row = ctk.CTkFrame(body, fg_color="transparent")
        key_row.grid(row=row, column=0, sticky="ew")
        key_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(key_row, text="Enregistrer sous la clé :").grid(row=0, column=0, padx=(0, 8))
        self._key_entry = ctk.CTkEntry(key_row)
        self._key_entry.insert(0, suggested_key)
        self._key_entry.grid(row=0, column=1, sticky="ew")
        row += 1

        self._error_label = ctk.CTkLabel(body, text="", text_color=_ERROR_COLOR, anchor="w")
        self._error_label.grid(row=row, column=0, sticky="ew", pady=(6, 0))
        row += 1

        # Boutons.
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.grid(row=row, column=0, sticky="ew", pady=(10, 0))
        buttons.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            buttons,
            text="Annuler le traitement",
            fg_color="transparent",
            border_width=1,
            text_color=("gray10", "gray90"),
            width=150,
            command=lambda: self._close(DialogAction.CANCEL),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            buttons, text="Ignorer tout", width=100, fg_color="gray50", hover_color="gray40",
            command=lambda: self._close(DialogAction.SKIP_ALL),
        ).grid(row=0, column=1, padx=(8, 0))
        ctk.CTkButton(
            buttons, text="Ignorer", width=80, fg_color="gray50", hover_color="gray40",
            command=lambda: self._close(DialogAction.SKIP),
        ).grid(row=0, column=2, padx=(8, 0))
        ctk.CTkButton(buttons, text="Valider", width=90, command=self._validate).grid(row=0, column=3, padx=(8, 0))

    def _build_value_widget(self, master: ctk.CTkFrame) -> ctk.CTkBaseClass:
        if self._field.field_type == FieldType.CHECKBOX:
            widget = ctk.CTkSegmentedButton(master, values=_CHECKBOX_VALUES)
            widget.set(_CHECKBOX_VALUES[0])
            return widget
        if self._field.options:
            # Liste de choix, mais saisie libre possible (valeur traduite au remplissage).
            widget = ctk.CTkComboBox(master, values=list(self._field.options))
            widget.set("")
            return widget
        return ctk.CTkEntry(master, placeholder_text="Saisissez la valeur…")

    # ------------------------------------------------------------------ #
    # Comportement
    # ------------------------------------------------------------------ #
    def _get_value(self) -> str:
        return str(self._value_widget.get()).strip()  # type: ignore[attr-defined]

    def _set_value(self, value: str) -> None:
        widget = self._value_widget
        if isinstance(widget, ctk.CTkEntry):
            widget.delete(0, "end")
            widget.insert(0, value)
        else:
            widget.set(value)  # type: ignore[attr-defined]

    def _on_existing_selected(self, choice: str) -> None:
        if choice == _NO_EXISTING:
            return
        key = choice.split(" : ", 1)[0]
        self._set_value(self._known_data[key])
        self._key_entry.delete(0, "end")
        self._key_entry.insert(0, key)
        self._save_var.set(True)
        self._on_save_toggled()

    def _on_save_toggled(self) -> None:
        self._key_entry.configure(state="normal" if self._save_var.get() else "disabled")

    def _validate(self) -> None:
        value = self._get_value()
        if not value:
            self._error_label.configure(text="Saisissez une valeur ou cliquez sur « Ignorer ».")
            return

        save = bool(self._save_var.get())
        key: str | None = None
        if save:
            try:
                key = normalize_key(self._key_entry.get())
            except InvalidKeyError:
                self._error_label.configure(text="La clé de sauvegarde est invalide.")
                return
        self.result = DialogResult(DialogAction.VALIDATE, Resolution(value=value, save=save, key=key))
        self.destroy()

    def _close(self, action: DialogAction) -> None:
        self.result = DialogResult(action)
        self.destroy()

    # ------------------------------------------------------------------ #
    # Fenêtre modale
    # ------------------------------------------------------------------ #
    def _center_on(self, master: ctk.CTk) -> None:
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_reqwidth()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _make_modal(self) -> None:
        # Sous Linux, grab_set échoue si la fenêtre n'est pas encore visible.
        self.wait_visibility()
        self.grab_set()
        self.lift()
        self.focus_force()
        self.after(50, self._value_widget.focus_set)
