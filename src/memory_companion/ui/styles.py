"""Application-wide Qt stylesheet.

The palette is deliberately calm and high-contrast; all sizes are in pixels so
the layout is stable at 100% and 150% Windows scaling.
"""

from __future__ import annotations

STYLESHEET = """
QWidget {
    font-family: "Segoe UI", "Segoe UI Variable", sans-serif;
    font-size: 13px;
    color: #1d2939;
}

QMainWindow, QDialog, #pageRoot {
    background: #f6f7f9;
}

#sidebar {
    background: #101828;
    border: none;
}

#sidebar QLabel#brand {
    color: #ffffff;
    font-size: 15px;
    font-weight: 600;
    padding: 4px 8px;
}

#sidebar QLabel#brandSub {
    color: #98a2b3;
    font-size: 11px;
    padding: 0 8px 8px 8px;
}

#sidebar QPushButton {
    color: #d0d5dd;
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 9px 12px;
    text-align: left;
    font-size: 13px;
}

#sidebar QPushButton:hover {
    background: #1d2939;
    color: #ffffff;
}

#sidebar QPushButton:checked {
    background: #2e90fa;
    color: #ffffff;
    font-weight: 600;
}

#topbar {
    background: #ffffff;
    border-bottom: 1px solid #e4e7ec;
}

#topbar QLabel {
    color: #475467;
}

QLabel[h1="true"] {
    font-size: 22px;
    font-weight: 600;
    color: #101828;
}

QLabel[h2="true"] {
    font-size: 17px;
    font-weight: 600;
    color: #101828;
}

QLabel[h3="true"] {
    font-size: 14px;
    font-weight: 600;
    color: #101828;
}

QLabel[muted="true"] {
    color: #667085;
}

QLabel[warning="true"] {
    color: #b42318;
}

QLabel[body="true"] {
    font-size: 13px;
    color: #1d2939;
}

QLabel[sender="true"] {
    font-weight: 600;
    font-size: 12px;
    color: #475467;
}

QFrame[card="true"], QFrame[suggestion="true"] {
    background: #ffffff;
    border: 1px solid #e4e7ec;
    border-radius: 10px;
}

QFrame[bubble="true"] {
    border-radius: 12px;
    border: 1px solid #e4e7ec;
    background: #ffffff;
}

QFrame[bubble="true"][role="user"] {
    background: #eaf2ff;
    border-color: #cddffb;
}

QFrame[bubble="true"][role="assistant"] {
    background: #ffffff;
}

QFrame[composer="true"] {
    background: #ffffff;
    border: 1px solid #d0d5dd;
    border-radius: 12px;
}

QFrame[banner="true"] {
    border-radius: 8px;
    background: #fef3f2;
    border: 1px solid #fecdca;
}

QFrame[banner="true"] QLabel {
    color: #b42318;
}

QLabel[chip="true"] {
    background: #eff8ff;
    border: 1px solid #b2ddff;
    border-radius: 10px;
    padding: 2px 8px;
    color: #175cd3;
    font-size: 11px;
    font-weight: 600;
}

QLabel[chip="true"][grounding="recorded"] {
    background: #ecfdf3;
    border-color: #abefc6;
    color: #067647;
}

QLabel[chip="true"][grounding="inferred"] {
    background: #fffaeb;
    border-color: #fedf89;
    color: #b54708;
}

QLabel[chip="true"][grounding="missing"] {
    background: #f2f4f7;
    border-color: #d0d5dd;
    color: #475467;
}

QLabel[chip="true"][grounding="conflicting"] {
    background: #fef3f2;
    border-color: #fecdca;
    color: #b42318;
}

QPushButton {
    background: #ffffff;
    border: 1px solid #d0d5dd;
    border-radius: 8px;
    padding: 6px 12px;
    color: #344054;
}

QPushButton:hover {
    background: #f9fafb;
    border-color: #98a2b3;
}

QPushButton:pressed {
    background: #f2f4f7;
}

QPushButton:disabled {
    color: #98a2b3;
    background: #f9fafb;
    border-color: #e4e7ec;
}

QPushButton[primary="true"] {
    background: #2e90fa;
    border-color: #2e90fa;
    color: #ffffff;
    font-weight: 600;
}

QPushButton[primary="true"]:hover {
    background: #1570ef;
    border-color: #1570ef;
}

QPushButton[primary="true"]:disabled {
    background: #b2ddff;
    border-color: #b2ddff;
    color: #ffffff;
}

QPushButton[flat="true"] {
    background: transparent;
    border: none;
    color: #175cd3;
    padding: 4px 6px;
}

QPushButton[flat="true"]:hover {
    background: #eff8ff;
}

QPushButton[danger="true"] {
    color: #b42318;
    border-color: #fecdca;
    background: #ffffff;
}

QPushButton[danger="true"]:hover {
    background: #fef3f2;
}

QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox {
    background: #ffffff;
    border: 1px solid #d0d5dd;
    border-radius: 8px;
    padding: 6px 8px;
    selection-background-color: #b2ddff;
    selection-color: #101828;
}

QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: #2e90fa;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QTableWidget {
    background: #ffffff;
    border: 1px solid #e4e7ec;
    border-radius: 10px;
    gridline-color: #f2f4f7;
    alternate-background-color: #fcfcfd;
}

QTableWidget::item {
    padding: 8px;
    border-bottom: 1px solid #f2f4f7;
}

QTableWidget::item:selected {
    background: #eff8ff;
    color: #101828;
}

QHeaderView::section {
    background: #f9fafb;
    border: none;
    border-bottom: 1px solid #e4e7ec;
    padding: 8px;
    color: #475467;
    font-weight: 600;
}

QGroupBox {
    background: #ffffff;
    border: 1px solid #e4e7ec;
    border-radius: 10px;
    margin-top: 14px;
    padding: 14px 12px 10px 12px;
    font-weight: 600;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: #101828;
}

QCheckBox {
    spacing: 8px;
}

QScrollArea {
    background: transparent;
    border: none;
}

QScrollArea > QWidget > QWidget {
    background: transparent;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: #d0d5dd;
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: #98a2b3;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
    height: 0;
}

QSplitter::handle {
    background: #e4e7ec;
}

QStatusBar {
    background: #ffffff;
    border-top: 1px solid #e4e7ec;
    color: #667085;
}
"""
