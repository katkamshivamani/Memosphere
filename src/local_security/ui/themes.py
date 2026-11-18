"""
Accessible, modern UI stylesheets for Light and Dark themes.
High-contrast, clean typography, large click targets for accessibility.
"""

DARK_THEME_QSS = """
QWidget {
    background-color: #121417;
    color: #E2E8F0;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    font-size: 14px;
}

QMainWindow, QDialog {
    background-color: #0F1115;
}

QTabWidget::pane {
    border: 1px solid #232936;
    background-color: #161A22;
    border-radius: 8px;
    top: -1px;
}

QTabBar::tab {
    background-color: #1A202C;
    color: #94A3B8;
    padding: 10px 20px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 600;
}

QTabBar::tab:selected {
    background-color: #161A22;
    color: #38BDF8;
    border-bottom: 2px solid #38BDF8;
}

QGroupBox {
    border: 1px solid #28303F;
    border-radius: 8px;
    margin-top: 18px;
    padding: 16px;
    font-weight: 600;
    font-size: 15px;
    color: #F1F5F9;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    left: 12px;
}

QPushButton {
    background-color: #2563EB;
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 10px 18px;
    font-weight: 600;
    min-height: 22px;
}

QPushButton:hover {
    background-color: #1D4ED8;
}

QPushButton:pressed {
    background-color: #1E40AF;
}

QPushButton:disabled {
    background-color: #334155;
    color: #64748B;
}

QPushButton#secondaryBtn {
    background-color: #1E293B;
    color: #E2E8F0;
    border: 1px solid #334155;
}

QPushButton#secondaryBtn:hover {
    background-color: #334155;
}

QPushButton#dangerBtn {
    background-color: #DC2626;
    color: #FFFFFF;
}

QPushButton#dangerBtn:hover {
    background-color: #B91C1C;
}

QLineEdit, QComboBox, QSpinBox {
    background-color: #1E2430;
    color: #F8FAFC;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 8px 12px;
    selection-background-color: #38BDF8;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #38BDF8;
    background-color: #222938;
}

QTableWidget {
    background-color: #161A22;
    gridline-color: #28303F;
    border: 1px solid #28303F;
    border-radius: 6px;
}

QHeaderView::section {
    background-color: #1E2430;
    color: #94A3B8;
    padding: 8px;
    border: none;
    border-bottom: 1px solid #28303F;
    font-weight: 600;
}

QLabel#titleLabel {
    font-size: 22px;
    font-weight: 700;
    color: #F8FAFC;
}

QLabel#subtitleLabel {
    font-size: 13px;
    color: #94A3B8;
}

QLabel#statusBadgeSuccess {
    background-color: #064E3B;
    color: #34D399;
    border-radius: 4px;
    padding: 4px 10px;
    font-weight: 600;
}

QLabel#statusBadgeWarning {
    background-color: #78350F;
    color: #FBBF24;
    border-radius: 4px;
    padding: 4px 10px;
    font-weight: 600;
}
"""

LIGHT_THEME_QSS = """
QWidget {
    background-color: #F8FAFC;
    color: #0F172A;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    font-size: 14px;
}

QMainWindow, QDialog {
    background-color: #FFFFFF;
}

QTabWidget::pane {
    border: 1px solid #E2E8F0;
    background-color: #FFFFFF;
    border-radius: 8px;
    top: -1px;
}

QTabBar::tab {
    background-color: #F1F5F9;
    color: #64748B;
    padding: 10px 20px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 600;
}

QTabBar::tab:selected {
    background-color: #FFFFFF;
    color: #0284C7;
    border-bottom: 2px solid #0284C7;
}

QGroupBox {
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    margin-top: 18px;
    padding: 16px;
    font-weight: 600;
    font-size: 15px;
    color: #0F172A;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    left: 12px;
}

QPushButton {
    background-color: #0284C7;
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 10px 18px;
    font-weight: 600;
    min-height: 22px;
}

QPushButton:hover {
    background-color: #0369A1;
}

QPushButton#secondaryBtn {
    background-color: #F1F5F9;
    color: #1E293B;
    border: 1px solid #CBD5E1;
}

QPushButton#secondaryBtn:hover {
    background-color: #E2E8F0;
}

QPushButton#dangerBtn {
    background-color: #EF4444;
    color: #FFFFFF;
}

QPushButton#dangerBtn:hover {
    background-color: #DC2626;
}

QLineEdit, QComboBox, QSpinBox {
    background-color: #FFFFFF;
    color: #0F172A;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 8px 12px;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #0284C7;
}

QTableWidget {
    background-color: #FFFFFF;
    gridline-color: #F1F5F9;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
}

QHeaderView::section {
    background-color: #F8FAFC;
    color: #475569;
    padding: 8px;
    border: none;
    border-bottom: 1px solid #E2E8F0;
    font-weight: 600;
}

QLabel#titleLabel {
    font-size: 22px;
    font-weight: 700;
    color: #0F172A;
}

QLabel#subtitleLabel {
    font-size: 13px;
    color: #64748B;
}

QLabel#statusBadgeSuccess {
    background-color: #D1FAE5;
    color: #065F46;
    border-radius: 4px;
    padding: 4px 10px;
    font-weight: 600;
}

QLabel#statusBadgeWarning {
    background-color: #FEF3C7;
    color: #92400E;
    border-radius: 4px;
    padding: 4px 10px;
    font-weight: 600;
}
"""
