"""Reusable table pages and an add-record dialog for the host application.

These pages are intentionally generic: each module (memories, people, places,
activities, routines, reminders) supplies column metadata, a loader callable and
an add-record callable.  The agent never uses these widgets - it only ever sees
read-only adapters and pending suggestions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from memory_companion.modules.common import parse_datetime


def format_timestamp(value: Any) -> str:
    parsed = parse_datetime(value)
    if parsed is None:
        return str(value or "")
    try:
        return parsed.astimezone().strftime("%d %b %Y, %H:%M")
    except (ValueError, OSError):
        return str(value or "")


class AddRecordDialog(QDialog):
    """Generic create dialog driven by a small field specification."""

    def __init__(
        self,
        title: str,
        fields: Sequence[dict],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        self._fields = list(fields)
        self._widgets: dict[str, QWidget] = {}

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        for spec in self._fields:
            key = spec["key"]
            kind = spec.get("kind", "text")
            if kind == "multiline":
                widget: QWidget = QPlainTextEdit()
                widget.setFixedHeight(84)
                widget.setPlaceholderText(spec.get("placeholder", ""))
            elif kind == "choice":
                widget = QComboBox()
                for value, label in spec.get("choices", []):
                    widget.addItem(label, value)
            else:
                widget = QLineEdit()
                widget.setPlaceholderText(spec.get("placeholder", ""))
            self._widgets[key] = widget
            form.addRow(spec["label"], widget)

        layout.addLayout(form)
        self._error = QLabel("")
        self._error.setProperty("warning", True)
        self._error.setWordWrap(True)
        layout.addWidget(self._error)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for spec in self._fields:
            key = spec["key"]
            widget = self._widgets[key]
            if isinstance(widget, QPlainTextEdit):
                values[key] = widget.toPlainText().strip()
            elif isinstance(widget, QComboBox):
                values[key] = widget.currentData()
            else:
                values[key] = widget.text().strip()
        return values

    def _accept(self) -> None:
        values = self.values()
        for spec in self._fields:
            if spec.get("required") and not str(values.get(spec["key"]) or "").strip():
                self._error.setText(f"{spec['label']} is required.")
                return
            if spec.get("kind") == "datetime" and values.get(spec["key"]):
                if parse_datetime(values[spec["key"]]) is None:
                    self._error.setText(
                        f"{spec['label']} must look like 2026-11-21T10:30 or "
                        "2026-11-21 10:30."
                    )
                    return
        self.accept()


class DataTablePage(QWidget):
    """Read-only table with an optional add action."""

    def __init__(
        self,
        *,
        title: str,
        subtitle: str,
        columns: Sequence[tuple[str, str]],
        loader: Callable[[str], list[dict]],
        add_title: Optional[str] = None,
        add_fields: Optional[Sequence[dict]] = None,
        add_handler: Optional[Callable[[dict], Any]] = None,
        delete_handler: Optional[Callable[[str], Any]] = None,
        empty_text: str = "Nothing saved yet.",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._columns = list(columns)
        self._loader = loader
        self._add_title = add_title
        self._add_fields = list(add_fields or [])
        self._add_handler = add_handler
        self._delete_handler = delete_handler
        self._empty_text = empty_text
        self._records: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        heading = QLabel(title)
        heading.setProperty("h1", True)
        header.addWidget(heading)
        header.addStretch(1)
        self._count = QLabel("")
        self._count.setProperty("muted", True)
        header.addWidget(self._count)
        layout.addLayout(header)

        sub = QLabel(subtitle)
        sub.setWordWrap(True)
        sub.setProperty("muted", True)
        layout.addWidget(sub)

        toolbar = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search…")
        self._search.returnPressed.connect(self.refresh)
        toolbar.addWidget(self._search, 1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        toolbar.addWidget(refresh)
        if self._add_handler is not None:
            add_button = QPushButton(f"Add {add_title or 'record'}")
            add_button.setProperty("primary", True)
            add_button.clicked.connect(self._add)
            toolbar.addWidget(add_button)
        layout.addLayout(toolbar)

        self._table = QTableWidget(0, len(self._columns))
        self._table.setHorizontalHeaderLabels([label for _, label in self._columns])
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setWordWrap(False)
        header_view = self._table.horizontalHeader()
        header_view.setStretchLastSection(True)
        layout.addWidget(self._table, 1)

        bottom = QHBoxLayout()
        self._empty = QLabel(self._empty_text)
        self._empty.setProperty("muted", True)
        bottom.addWidget(self._empty, 1)
        if self._delete_handler is not None:
            self._delete = QPushButton("Delete selected")
            self._delete.setProperty("danger", True)
            self._delete.clicked.connect(self._delete_selected)
            bottom.addWidget(self._delete)
        layout.addLayout(bottom)

        self.refresh()

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        query = self._search.text().strip()
        try:
            records = self._loader(query)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Could not load records",
                f"The records could not be loaded ({type(exc).__name__}).",
            )
            return
        self._records = list(records or [])
        self._table.setRowCount(len(self._records))
        for row_index, record in enumerate(self._records):
            for column_index, (key, _label) in enumerate(self._columns):
                value = record.get(key, "")
                if key.endswith("_at") and value:
                    value = format_timestamp(value)
                item = QTableWidgetItem(str(value or ""))
                item.setToolTip(str(value or ""))
                self._table.setItem(row_index, column_index, item)
        self._table.resizeColumnsToContents()
        self._count.setText(f"{len(self._records)} record(s)")
        self._empty.setVisible(not self._records)
        self._table.setVisible(bool(self._records))

    # ------------------------------------------------------------------ #
    def _add(self) -> None:
        dialog = AddRecordDialog(self._add_title or "Add record", self._add_fields, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        try:
            if self._add_handler is not None:
                self._add_handler(values)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Record not saved",
                f"The record could not be saved: {exc}",
            )
            return
        self.refresh()

    def _delete_selected(self) -> None:
        rows = self._table.selectionModel().selectedRows() if self._table.selectionModel() else []
        if not rows:
            return
        record = self._records[rows[0].row()]
        title = record.get("title") or record.get("name") or "this record"
        confirm = QMessageBox.question(
            self,
            "Delete record",
            f"Permanently delete “{title}”? This cannot be undone.",
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            if self._delete_handler is not None:
                self._delete_handler(str(record.get("id")))
        except Exception as exc:
            QMessageBox.warning(self, "Not deleted", f"The record could not be deleted: {exc}")
            return
        self.refresh()
