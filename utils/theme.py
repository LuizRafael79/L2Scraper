class DarkTheme:
    PRIMARY = "#1a1b26"
    SECONDARY = "#24283b"
    TERTIARY = "#414868"
    ACCENT = "#7aa2f7"
    SUCCESS = "#9ece6a"
    WARNING = "#e0af68"
    ERROR = "#f7768e"
    TEXT_PRIMARY = "#c0caf5"
    TEXT_SECONDARY = "#a9b1d6"
    
    @staticmethod
    def get_stylesheet():
        return f"""
        QMainWindow, QWidget {{
            background-color: {DarkTheme.PRIMARY};
            color: {DarkTheme.TEXT_PRIMARY};
            font-family: 'Segoe UI', Arial, sans-serif;
        }}
        
        QListWidget {{
            background-color: {DarkTheme.SECONDARY};
            border: 1px solid {DarkTheme.TERTIARY};
            border-radius: 8px;
            padding: 5px;
            outline: none;
        }}
        
        QListWidget::item {{
            padding: 10px;
            border-radius: 5px;
            margin: 2px;
        }}
        
        QListWidget::item:selected {{
            background-color: {DarkTheme.ACCENT};
            color: white;
        }}
        
        QListWidget::item:hover {{
            background-color: {DarkTheme.TERTIARY};
        }}
        
        QPushButton {{
            background-color: {DarkTheme.ACCENT};
            color: white;
            border: none;
            padding: 10px 15px;
            border-radius: 6px;
            font-weight: bold;
            min-width: 80px;
        }}
        
        QPushButton:hover {{
            background-color: #8baaf8;
        }}
        
        QPushButton:pressed {{
            background-color: #6b94f6;
        }}
        
        QPushButton:disabled {{
            background-color: {DarkTheme.TERTIARY};
            color: {DarkTheme.TEXT_SECONDARY};
        }}
        
        QProgressBar {{
            border: none;
            background-color: {DarkTheme.SECONDARY};
            border-radius: 4px;
            text-align: center;
            color: {DarkTheme.TEXT_PRIMARY};
        }}
        
        QProgressBar::chunk {{
            background-color: {DarkTheme.SUCCESS};
            border-radius: 4px;
        }}
        
        /* Estilo padrão para QTextEdit */
        QTextEdit {{
            background-color: {DarkTheme.SECONDARY};
            border: 1px solid {DarkTheme.TERTIARY};
            border-radius: 8px;
            padding: 10px;
            color: {DarkTheme.TEXT_PRIMARY};
        }}
        
        /* Estilo ESPECÍFICO para o XML Editor - fonte monoespaçada */
        QTextEdit#xmlEditor {{
            background-color: {DarkTheme.SECONDARY};
            border: 1px solid {DarkTheme.TERTIARY};
            border-radius: 8px;
            padding: 10px;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            /* NÃO definir font-size aqui - deixar QFont controlar */
            color: {DarkTheme.TEXT_PRIMARY};
            selection-background-color: {DarkTheme.ACCENT};
        }}
        
        QLineEdit {{
            background-color: {DarkTheme.SECONDARY};
            border: 1px solid {DarkTheme.TERTIARY};
            border-radius: 6px;
            padding: 8px;
            color: {DarkTheme.TEXT_PRIMARY};
        }}
        
        QLineEdit:focus {{
            border: 1px solid {DarkTheme.ACCENT};
        }}
        
        QComboBox {{
            background-color: {DarkTheme.SECONDARY};
            border: 1px solid {DarkTheme.TERTIARY};
            border-radius: 6px;
            padding: 6px;
            color: {DarkTheme.TEXT_PRIMARY};
        }}
        
        QComboBox:hover {{
            border: 1px solid {DarkTheme.ACCENT};
        }}
        
        QComboBox::drop-down {{
            border: none;
        }}
        
        QComboBox QAbstractItemView {{
            background-color: {DarkTheme.SECONDARY};
            border: 1px solid {DarkTheme.TERTIARY};
            selection-background-color: {DarkTheme.ACCENT};
            color: {DarkTheme.TEXT_PRIMARY};
        }}
        
        QSpinBox {{
            background-color: {DarkTheme.SECONDARY};
            border: 1px solid {DarkTheme.TERTIARY};
            border-radius: 6px;
            padding: 6px;
            color: {DarkTheme.TEXT_PRIMARY};
        }}
        
        QSpinBox:focus {{
            border: 1px solid {DarkTheme.ACCENT};
        }}
        
        QSpinBox::up-button, QSpinBox::down-button {{
            background-color: {DarkTheme.TERTIARY};
            border: none;
            width: 16px;
        }}
        
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
            background-color: {DarkTheme.ACCENT};
        }}
        
        QGroupBox {{
            font-weight: bold;
            border: 1px solid {DarkTheme.TERTIARY};
            border-radius: 8px;
            margin-top: 10px;
            padding-top: 10px;
        }}
        
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px 0 5px;
        }}
        
        QLabel {{
            color: {DarkTheme.TEXT_PRIMARY};
        }}
        
        /* Remover estilo de QSplitter - deixar padrão nativo do Qt */
        
        QTabWidget::pane {{
            border: 1px solid {DarkTheme.TERTIARY};
            border-radius: 8px;
        }}
        
        QTabBar::tab {{
            background-color: {DarkTheme.SECONDARY};
            color: {DarkTheme.TEXT_PRIMARY};
            padding: 8px 16px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }}
        
        QTabBar::tab:selected {{
            background-color: {DarkTheme.ACCENT};
            color: white;
        }}
        
        QTabBar::tab:hover:!selected {{
            background-color: {DarkTheme.TERTIARY};
        }}
        """