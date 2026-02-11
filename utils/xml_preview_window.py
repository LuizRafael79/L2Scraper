from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                           QPushButton, QLabel, QTextEdit, QComboBox,
                           QSpinBox, QCheckBox, QGroupBox, QGridLayout)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QSyntaxHighlighter, QTextDocument, QColor, QTextCharFormat
import re

class XMLSyntaxHighlighter(QSyntaxHighlighter):
    """Syntax highlighter para XML"""
    def __init__(self, document):
        super().__init__(document)
        
        self.tag_format = QTextCharFormat()
        self.tag_format.setForeground(QColor("#569CD6"))
        self.tag_format.setFontWeight(700)
        
        self.attr_format = QTextCharFormat()
        self.attr_format.setForeground(QColor("#9CDCFE"))
        
        self.value_format = QTextCharFormat()
        self.value_format.setForeground(QColor("#CE9178"))
        
        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor("#6A9955"))
        self.comment_format.setFontItalic(True)

    def highlightBlock(self, text):
        # Comentários (primeiro, pra sobrescrever tudo)
        comment_pattern = r'<!--.*?-->'
        for match in re.finditer(comment_pattern, text):
            self.setFormat(match.start(), match.end() - match.start(), self.comment_format)
        
        # Tags
        tag_pattern = r'</?[a-zA-Z0-9\-:]+(?:\s|>|/?>)'
        for match in re.finditer(tag_pattern, text):
            self.setFormat(match.start(), match.end() - match.start(), self.tag_format)
        
        # Attributes
        attr_pattern = r'[a-zA-Z0-9\-:]+(?=\s*=)'
        for match in re.finditer(attr_pattern, text):
            self.setFormat(match.start(), match.end() - match.start(), self.attr_format)
        
        # Values
        value_pattern = r'"[^"]*"|\'[^\']*\''
        for match in re.finditer(value_pattern, text):
            self.setFormat(match.start(), match.end() - match.start(), self.value_format)


class XMLPreviewWindow(QMainWindow):
    apply_signal = pyqtSignal()  # Sinal para aplicar as mudanças
    
    def __init__(self, xml_text: str, parent=None):
        super().__init__(parent)
        self.xml_text = xml_text
        self.original_xml = xml_text
        self.setup_ui()
        
    def setup_ui(self):
        self.setWindowTitle("XML Preview - SkillTree Builder")
        self.setGeometry(150, 150, 1400, 800)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
        # --- TOOLBAR ---
        toolbar_layout = QHBoxLayout()
        
        toolbar_layout.addWidget(QLabel("Display Options:"))
        
        self.skill_filter = QComboBox()
        self.skill_filter.addItems(["All Content", "Skills Only", "Comments Only"])
        self.skill_filter.currentTextChanged.connect(self.update_preview)
        toolbar_layout.addWidget(self.skill_filter)
        
        self.line_numbers_check = QCheckBox("Line Numbers")
        self.line_numbers_check.setChecked(True)
        self.line_numbers_check.stateChanged.connect(self.update_preview)
        toolbar_layout.addWidget(self.line_numbers_check)
        
        self.editable_check = QCheckBox("Enable Editing")
        self.editable_check.setChecked(False)
        self.editable_check.stateChanged.connect(self.toggle_editing)
        toolbar_layout.addWidget(self.editable_check)
        
        toolbar_layout.addStretch()
        
        main_layout.addLayout(toolbar_layout)
        
        # --- STATISTICS ---
        stats_group = QGroupBox("Statistics")
        stats_layout = QGridLayout(stats_group)
        
        self.total_skills = QLabel("Total Skills: 0")
        self.total_comments = QLabel("Comments: 0")
        self.total_lines = QLabel("Lines: 0")
        self.file_size = QLabel("File Size: 0 KB")
        
        stats_layout.addWidget(self.total_skills, 0, 0)
        stats_layout.addWidget(self.total_comments, 0, 1)
        stats_layout.addWidget(self.total_lines, 0, 2)
        stats_layout.addWidget(self.file_size, 0, 3)
        
        main_layout.addWidget(stats_group)
        
        # --- XML EDITOR ---
        editor_group = QGroupBox("XML Content (with comments preserved)")
        editor_layout = QVBoxLayout(editor_group)
        
        self.xml_editor = QTextEdit()
        self.xml_editor.setReadOnly(True)
        self.xml_editor.setFont(QFont("Consolas", 10))
        self.xml_editor.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #444;
            }
        """)
        
        # Aplicar syntax highlighting
        self.highlighter = XMLSyntaxHighlighter(self.xml_editor.document())
        
        editor_layout.addWidget(self.xml_editor)
        main_layout.addWidget(editor_group, 1)
        
        # --- BUTTONS ---
        button_layout = QHBoxLayout()
        
        self.copy_btn = QPushButton("📋 Copy to Clipboard")
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        button_layout.addWidget(self.copy_btn)
        
        button_layout.addStretch()
        
        self.cancel_btn = QPushButton("❌ Cancel")
        self.cancel_btn.clicked.connect(self.close)
        button_layout.addWidget(self.cancel_btn)
        
        self.apply_btn = QPushButton("✅ Apply Changes")
        self.apply_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.apply_btn.clicked.connect(self.apply_changes)
        button_layout.addWidget(self.apply_btn)
        
        main_layout.addLayout(button_layout)
        
        # Exibir preview inicial
        self.update_preview()
        self.update_statistics()
    
    def toggle_editing(self, state):
        """Habilita/desabilita edição"""
        self.xml_editor.setReadOnly(not state)
        if state:
            self.xml_editor.setStyleSheet("""
                QTextEdit {
                    background-color: #2d2d2d;
                    color: #d4d4d4;
                    border: 2px solid #4CAF50;
                }
            """)
        else:
            self.xml_editor.setStyleSheet("""
                QTextEdit {
                    background-color: #1e1e1e;
                    color: #d4d4d4;
                    border: 1px solid #444;
                }
            """)
    
    def update_preview(self):
        """Atualiza o preview baseado nos filtros"""
        filter_type = self.skill_filter.currentText()
        
        if filter_type == "Skills Only":
            # Mostrar apenas linhas com skills
            lines = self.xml_text.split('\n')
            filtered_lines = [line for line in lines 
                            if '<skill' in line or '</skill>' in line or 'skillTree' in line]
            xml_content = '\n'.join(filtered_lines)
        
        elif filter_type == "Comments Only":
            # Mostrar apenas comentários
            lines = self.xml_text.split('\n')
            filtered_lines = [line for line in lines if '<!--' in line or '-->' in line]
            xml_content = '\n'.join(filtered_lines)
        
        else:
            # Mostrar tudo
            xml_content = self.xml_text
        
        # Adicionar line numbers
        if self.line_numbers_check.isChecked():
            lines = xml_content.split('\n')
            numbered_lines = [f"{i+1:4d} | {line}" for i, line in enumerate(lines)]
            xml_content = '\n'.join(numbered_lines)
        
        self.xml_editor.setPlainText(xml_content)
    
    def update_statistics(self):
        """Atualiza as estatísticas"""
        lines = self.xml_text.split('\n')
        
        # Contar skills
        total_skills = sum(1 for line in lines if '<skill ' in line)
        
        # Contar comentários
        total_comments = sum(1 for line in lines if '<!--' in line)
        
        # Calcular tamanho do arquivo
        file_size_kb = len(self.xml_text.encode('utf-8')) / 1024
        
        self.total_skills.setText(f"Total Skills: {total_skills}")
        self.total_comments.setText(f"Comments: {total_comments}")
        self.total_lines.setText(f"Lines: {len(lines)}")
        self.file_size.setText(f"File Size: {file_size_kb:.2f} KB")
    
    def copy_to_clipboard(self):
        """Copia o XML para clipboard"""
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.xml_text)
        self.statusBar().showMessage("✅ XML copied to clipboard!", 3000)
    
    def apply_changes(self):
        """Emite sinal para aplicar as mudanças"""
        # Se editou, atualizar o xml_text
        if not self.xml_editor.isReadOnly():
            # Remover line numbers se existir
            content = self.xml_editor.toPlainText()
            if self.line_numbers_check.isChecked():
                lines = content.split('\n')
                lines = [line.split('|', 1)[1].strip() if '|' in line else line for line in lines]
                content = '\n'.join(lines)
            self.xml_text = content
        
        self.apply_signal.emit()
        self.statusBar().showMessage("✅ Changes applied!", 3000)
        self.close()
    
    def get_modified_xml(self) -> str:
        """Retorna o XML modificado (como texto)"""
        # Se foi editado, pegar do editor
        if not self.xml_editor.isReadOnly() and self.editable_check.isChecked():
            content = self.xml_editor.toPlainText()
            
            # Remover line numbers se existir
            if self.line_numbers_check.isChecked():
                lines = content.split('\n')
                lines = [line.split('|', 1)[1].strip() if '|' in line else line for line in lines]
                content = '\n'.join(lines)
            
            return content
        
        # Senão, retornar o original
        return self.xml_text