# tabs/item_builder_tab.py
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
                           QListWidget, QTabWidget, QListWidgetItem, QTextEdit, QPushButton,
                           QLabel, QLineEdit, QSpinBox, QProgressBar, QComboBox,
                           QMessageBox, QDialog, QFrame)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from lxml import etree
import re
import os
import json
from pathlib import Path
from typing import Optional, TYPE_CHECKING

# Imports locais
from workers.scanner_worker import ItemBuilderWorker
from core.handlers.item_handler import ItemHandler
from models.problem_model import ProblemModel
from ui.multilevel_dialog import MultilevelSkillDialog 


if TYPE_CHECKING:
    from config.config_manager import ConfigManager
    from core.database import DatabaseManager
    from core.handlers.xml_handler import XMLHandler
    from core.handlers.scraper_handler import ScraperHandler
    from core.handlers.skill_handler import SkillHandler

class ItemBuilderTab(QWidget):
    def __init__(
        self, 
        config: "ConfigManager", 
        database: "DatabaseManager", 
        xml_handler: "XMLHandler", 
        scraper_handler: "ScraperHandler", 
        skill_handler: "SkillHandler"
    ):
        super().__init__()
        self.config = config
        self.database = database
        self.xml_handler = xml_handler
        self.scraper_handler = scraper_handler
        self.skill_handler = skill_handler
       
        # Inicializa com site_type padrão (será atualizado pelo combo)
        self.site_type = "main" 
        
        # Inicializa o ItemHandler
        self.item_handler = ItemHandler(
            self.site_type, 
            self.config, 
            self.database, 
            self.skill_handler, 
            self.scraper_handler, 
            self.xml_handler
        )
        
        self.builder_worker = None
        
        # Listas de dados
        self.problems = []
        self.filtered_problems = []
        self.box_problems = []
        self.skill_problems = []
        self.filtered_box_problems = []
        self.filtered_skill_problems = []
        
        self.current_problem: Optional[ProblemModel] = None
        self.current_selection_type = "box"  # "box" ou "skill"
        
        self.setup_ui()
          
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # ===== CONTROLES SUPERIORES =====
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)
        
        controls_layout.addWidget(QLabel("Site Type:"))
        self.site_type_combo = QComboBox()
        self.site_type_combo.addItems(["Main", "Essence"]) # Ordem ajustada
        self.site_type_combo.currentTextChanged.connect(self.on_site_type_changed)
        self.site_type_combo.setMaximumWidth(120)
        controls_layout.addWidget(self.site_type_combo)
        
        self.scan_btn = QPushButton("🔍 Scan Items")
        self.scan_btn.clicked.connect(self.start_scan)
        self.scan_btn.setMaximumWidth(120)
        controls_layout.addWidget(self.scan_btn)
        
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by item ID...")
        self.filter_edit.setMaximumWidth(200)
        self.filter_edit.textChanged.connect(self.filter_items)
        controls_layout.addWidget(self.filter_edit)
        
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All Issues", "No Scraper Data", "No XML", "XML Incorrect", "Has Data"])
        self.filter_combo.currentTextChanged.connect(self.filter_items)
        self.filter_combo.setMaximumWidth(150)
        controls_layout.addWidget(self.filter_combo)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(200)
        controls_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Ready - Select site type and click 'Scan Items'")
        controls_layout.addWidget(self.status_label)
        
        controls_layout.addStretch()
        layout.addLayout(controls_layout)
        
        # ===== ÁREA PRINCIPAL =====
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setHandleWidth(8)
        main_splitter.setChildrenCollapsible(False)
        
        # --- COLUNA ESQUERDA ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(5)
        
        # Box header
        box_header = QHBoxLayout()
        box_header.addWidget(QLabel("<b>Box needing fix:</b>"))
        self.box_count_label = QLabel("0 boxes")
        box_header.addWidget(self.box_count_label)
        box_header.addStretch()
        left_layout.addLayout(box_header)
        
        self.box_items_list = QListWidget()
        self.box_items_list.itemClicked.connect(self.on_box_item_selected)
        left_layout.addWidget(self.box_items_list, 1)
        
        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setMaximumHeight(2)
        left_layout.addWidget(separator)
        
        # Skills header
        skills_header = QHBoxLayout()
        skills_header.addWidget(QLabel("<b>Skills needing fix:</b>"))
        self.skills_count_label = QLabel("0 skills")
        skills_header.addWidget(self.skills_count_label)

        self.multilevel_btn = QPushButton("📊 Multilevel Skills")
        self.multilevel_btn.clicked.connect(self.open_multilevel_dialog) 
        self.multilevel_btn.setEnabled(False)
        skills_header.addWidget(self.multilevel_btn)

        skills_header.addStretch()
        left_layout.addLayout(skills_header)
        
        self.skills_list = QListWidget()
        self.skills_list.itemClicked.connect(self.on_skill_item_selected)
        left_layout.addWidget(self.skills_list, 1)
        
        # Mass Actions
        mass_actions = QHBoxLayout()
        self.fix_all_btn = QPushButton("🔧 Auto-Fix All")
        self.fix_all_btn.clicked.connect(self.auto_fix_all)
        self.fix_all_btn.setEnabled(False)
        mass_actions.addWidget(self.fix_all_btn)

        self.export_btn = QPushButton("📋 Export")
        self.export_btn.clicked.connect(self.export_problem_list)
        self.export_btn.setEnabled(False)
        mass_actions.addWidget(self.export_btn)
        
        left_layout.addLayout(mass_actions)
        
        # --- COLUNA MEIO ---
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(5)
        
        self.editor_tabs = QTabWidget()
        self.editor_tabs.setTabPosition(QTabWidget.TabPosition.North)
        center_layout.addWidget(self.editor_tabs)
        
        # Tab Item
        self.item_tab = QWidget()
        item_tab_layout = QVBoxLayout(self.item_tab)
        item_tab_layout.setContentsMargins(0, 0, 0, 0)
        
        item_header = QHBoxLayout()
        item_header.addWidget(QLabel("<b>Item XML</b>"))
        
        self.format_item_btn = QPushButton("✨ Format")
        self.format_item_btn.clicked.connect(self.format_item_xml)
        item_header.addWidget(self.format_item_btn)
        
        self.validate_item_btn = QPushButton("✓ Validate")
        self.validate_item_btn.clicked.connect(self.validate_item_xml)
        item_header.addWidget(self.validate_item_btn)
        
        item_header.addStretch()
        item_tab_layout.addLayout(item_header)
        
        self.item_xml_editor = QTextEdit()
        self.item_xml_editor.setAcceptRichText(False)
        item_tab_layout.addWidget(self.item_xml_editor)
        
        # Tab Skill
        self.skill_tab = QWidget()
        skill_tab_layout = QVBoxLayout(self.skill_tab)
        skill_tab_layout.setContentsMargins(0, 0, 0, 0)
        
        skill_header = QHBoxLayout()
        skill_header.addWidget(QLabel("<b>Skill XML</b>"))
        
        self.format_skill_btn = QPushButton("✨ Format")
        self.format_skill_btn.clicked.connect(self.format_skill_xml)
        skill_header.addWidget(self.format_skill_btn)
        
        self.validate_skill_btn = QPushButton("✓ Validate")
        self.validate_skill_btn.clicked.connect(self.validate_skill_xml)
        skill_header.addWidget(self.validate_skill_btn)
        
        skill_header.addStretch()
        skill_tab_layout.addLayout(skill_header)
        
        self.skill_xml_editor = QTextEdit()
        self.skill_xml_editor.setAcceptRichText(False)
        skill_tab_layout.addWidget(self.skill_xml_editor)
        
        self.editor_tabs.addTab(self.item_tab, "📦 Item XML")
        self.editor_tabs.addTab(self.skill_tab, "⚡ Skill XML")
        
        # Font Controls
        font_controls = QHBoxLayout()
        font_controls.addWidget(QLabel("Font:"))
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(12)
        self.font_size_spin.valueChanged.connect(self.change_editor_font_size)
        font_controls.addWidget(self.font_size_spin)
        font_controls.addStretch()
        center_layout.addLayout(font_controls)
        
        # Action Buttons
        action_row1 = QHBoxLayout()
        self.save_item_btn = QPushButton("💾 Save Item")
        self.save_item_btn.clicked.connect(self.save_item_xml)
        self.save_item_btn.setEnabled(False)
        action_row1.addWidget(self.save_item_btn)
        
        self.save_skill_btn = QPushButton("💾 Save Skill")
        self.save_skill_btn.clicked.connect(self.save_skill_xml)
        self.save_skill_btn.setEnabled(False)
        action_row1.addWidget(self.save_skill_btn)
        
        self.auto_fix_item_btn = QPushButton("🔧 Auto-Fix Item")
        self.auto_fix_item_btn.clicked.connect(self.auto_fix_item)
        self.auto_fix_item_btn.setEnabled(False)
        action_row1.addWidget(self.auto_fix_item_btn)
        
        self.auto_fix_skill_btn = QPushButton("🔧 Auto-Fix Skill")
        self.auto_fix_skill_btn.clicked.connect(self.auto_fix_skill)
        self.auto_fix_skill_btn.setEnabled(False)
        action_row1.addWidget(self.auto_fix_skill_btn)
        center_layout.addLayout(action_row1)
        
        action_row2 = QHBoxLayout()
        self.prev_btn = QPushButton("⬅️ Previous")
        self.prev_btn.clicked.connect(self.previous_item)
        self.prev_btn.setEnabled(False)
        action_row2.addWidget(self.prev_btn)

        self.next_btn = QPushButton("➡️ Next")
        self.next_btn.clicked.connect(self.next_item)
        self.next_btn.setEnabled(False)
        action_row2.addWidget(self.next_btn)
        action_row2.addStretch()
        center_layout.addLayout(action_row2)
        
        self.editor_tabs.setTabEnabled(1, False)
        
        # --- COLUNA DIREITA ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.setHandleWidth(8)
        
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(5, 5, 5, 5)
        info_layout.addWidget(QLabel("<b>Item Information</b>"))
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        info_layout.addWidget(self.info_text)
        
        scraper_widget = QWidget()
        scraper_layout = QVBoxLayout(scraper_widget)
        scraper_layout.setContentsMargins(5, 5, 5, 5)
        scraper_layout.addWidget(QLabel("<b>Scraper Data Preview</b>"))
        self.scraper_text = QTextEdit()
        self.scraper_text.setReadOnly(True)
        scraper_layout.addWidget(self.scraper_text)
        
        right_splitter.addWidget(info_widget)
        right_splitter.addWidget(scraper_widget)
        right_splitter.setStretchFactor(0, 1)
        right_splitter.setStretchFactor(1, 2)
        
        right_layout.addWidget(right_splitter)
        
        main_splitter.addWidget(left_widget)
        main_splitter.addWidget(center_widget)
        main_splitter.addWidget(right_widget)
        
        main_splitter.setStretchFactor(0, 2)
        main_splitter.setStretchFactor(1, 5)
        main_splitter.setStretchFactor(2, 2)
        
        left_widget.setMinimumWidth(200)
        center_widget.setMinimumWidth(400)
        right_widget.setMinimumWidth(250)
        
        layout.addWidget(main_splitter, stretch=1)
        
        self.update_editor_font(12)

    def update_editor_font(self, size):
        from PyQt6.QtGui import QFont, QFontMetrics
        font = QFont("Consolas", size)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.item_xml_editor.setFont(font)
        self.skill_xml_editor.setFont(font)
        
        metrics = QFontMetrics(font)
        space_width = metrics.horizontalAdvance(' ')
        self.item_xml_editor.setTabStopDistance(space_width * 4)
        self.skill_xml_editor.setTabStopDistance(space_width * 4)

    def change_editor_font_size(self, size):
        self.update_editor_font(size)
        
    def on_site_type_changed(self):
        site_type_selection = self.site_type_combo.currentText().lower()
        self.site_type = site_type_selection # Atualiza estado

        # Atualiza o handler
        self.item_handler = ItemHandler(
            site_type=site_type_selection,
            config=self.config,
            database=self.database,
            skill_handler=self.skill_handler,
            scraper_handler=self.scraper_handler,
            xml_handler=self.xml_handler
        )

        self.status_label.setText(f"Site: {site_type_selection} - Click 'Scan Items' to begin")
        
        self.box_items_list.clear()
        self.skills_list.clear()
        self.problems = []
        self.box_problems = []
        self.skill_problems = []
        self.filtered_problems = []
        self.clear_editor()
        self.box_count_label.setText("0 boxes")
        self.skills_count_label.setText("0 skills")
        self.fix_all_btn.setEnabled(False)
        self.export_btn.setEnabled(False)

    def show_skill_errors_window(self, errors: list):
        dialog = QDialog(self)
        dialog.setWindowTitle("Skill Processing Errors")
        dialog.resize(800, 400)
        layout = QVBoxLayout(dialog)
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        content = "SKILL PROCESSING ERRORS\n" + "=" * 80 + "\n\n" + "\n".join(errors)
        text_edit.setText(content)
        layout.addWidget(text_edit)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        dialog.exec()
    
    def start_scan(self):
        site_type_selection = self.site_type_combo.currentText().lower()
        
        # Passa apenas o site selecionado
        site_types = [site_type_selection]
        
        self.scan_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.box_items_list.clear()
        self.status_label.setText(f"Scanning {site_type_selection}...")
        
        self.builder_worker = ItemBuilderWorker(self.config, site_types)
        self.builder_worker.progress_signal.connect(self.update_progress)
        self.builder_worker.log_signal.connect(self.update_status)
        self.builder_worker.items_loaded_signal.connect(self.on_items_loaded)
        self.builder_worker.start()
        
    def update_progress(self, current, total, status):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(status)
        
    def update_status(self, message):
        self.status_label.setText(message)
        
    def on_items_loaded(self, problems):
        self.problems = problems
        self.box_problems = []
        self.skill_problems = []
        
        for problem in problems:
            scraper_data = problem.get('scraper_data', {})
            has_skills = False
            skill_id = None
            
            if scraper_data:
                scraping_info = scraper_data.get('scraping_info', {})
                has_skills = scraping_info.get('has_skills', False)
                skill_id = self.scraper_handler.get_skill_id(scraper_data)
            
            # ✅ SEPARA CORRETAMENTE
            if has_skills and skill_id:
                self.skill_problems.append(problem)
            else:
                self.box_problems.append(problem)
        
        self.filtered_box_problems = self.box_problems.copy()
        self.filtered_skill_problems = self.skill_problems.copy()  # ✅ COPIA TODAS
        self.filtered_problems = self.box_problems + self.skill_problems
        
        self.scan_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.fix_all_btn.setEnabled(len(problems) > 0)
        self.export_btn.setEnabled(len(problems) > 0)
        
        self.populate_box_items_list()
        self.populate_skills_list()
        self.status_label.setText(f"Found {len(self.box_problems)} boxes and {len(self.skill_problems)} skills needing fix")
        
    def populate_box_items_list(self):
        """Popula lista com TODOS os boxes (ok + problema)"""
        self.box_items_list.clear()
        for problem in self.filtered_box_problems:
            needs_fix = problem.get('needs_fix', True)
            item_text = f"{problem['item_id']} ({problem['site_type']}) - {len(problem['issues'])} issues"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, problem)
            
            # ✅ CORES ATUALIZADAS
            if needs_fix:
                if not problem.get('has_scraper_data'):
                    item.setForeground(Qt.GlobalColor.red)  # Sem scraper
                elif not problem.get('has_xml'):
                    item.setForeground(Qt.GlobalColor.yellow)  # Sem XML
                else:
                    item.setForeground(Qt.GlobalColor.cyan)  # XML incorreto
            else:
                item.setForeground(Qt.GlobalColor.white)  # ✅ OK - branco
                
            self.box_items_list.addItem(item)
        self.box_count_label.setText(f"{len(self.filtered_box_problems)} boxes")

    def populate_skills_list(self):
        """Popula lista de skills SINGLE LEVEL - TODOS"""
        self.skills_list.clear()
        
        multilevel_skills_set = set()
        if self.site_type == "main":
            json_filename = f"multilevel_skills_main.json"
            if os.path.exists(json_filename):
                try:
                    with open(json_filename, 'r', encoding='utf-8') as f:
                        multilevel_data = json.load(f)
                        multilevel_skills_set = set(multilevel_data.keys())
                        print(f"✅ Carregadas {len(multilevel_skills_set)} skills multilevel")
                except Exception as e:
                    print(f"⚠️ Erro ao carregar multilevel JSON: {e}")
        
        self.multilevel_skills_set = multilevel_skills_set
        
        skills_grouped = {}
        
        for problem in self.filtered_skill_problems:
            scraper_data = problem.get('scraper_data', {})
            if not scraper_data: 
                continue
            
            skill_id = self.scraper_handler.get_skill_id(scraper_data)
            
            skill_level = None
            skill_data = scraper_data.get('skill_data', {})
            if skill_data:
                sl = skill_data.get('skill_level')
                skill_level = int(sl) if sl is not None else None
            
            if not skill_id or skill_level is None: 
                continue
            
            if skill_id not in skills_grouped:
                skills_grouped[skill_id] = []
            
            skills_grouped[skill_id].append({
                'problem': problem,
                'level': skill_level,
                'item_id': problem['item_id']
            })
        
        multilevel_count = len(multilevel_skills_set)
        single_level_count = 0
        
        for skill_id, items in sorted(skills_grouped.items()):
            if skill_id in multilevel_skills_set:
                print(f"🚫 Skill {skill_id} EXTIRPADA (está no JSON multilevel)")
                continue
            
            item_data = items[0]
            problem = item_data['problem']
            skill_level = item_data['level']
            item_id = item_data['item_id']
            site_type = problem['site_type']
            
            skill_name = self.skill_handler.get_skill_name_from_skill_id(skill_id, site_type) or "Unknown"
            item_name = self.skill_handler.get_item_name_from_item_id(item_id, site_type) or f"Item {item_id}"
            
            item_text = f"Skill {skill_id} Level {skill_level} - Item {item_id} ({item_name})"
            list_item = QListWidgetItem(item_text)
            
            # ✅ COR BASEADA EM needs_fix
            needs_fix = problem.get('needs_fix', True)
            list_item.setData(Qt.ItemDataRole.UserRole, {
                'type': 'skill_single',
                'skill_id': skill_id,
                'skill_level': skill_level,
                'problem': problem,
                'site_type': site_type
            })
            
            if needs_fix:
                list_item.setForeground(Qt.GlobalColor.magenta)
            else:
                list_item.setForeground(Qt.GlobalColor.white)  # ✅ OK - branco
                
            self.skills_list.addItem(list_item)
            single_level_count += 1
        
        self.skills_count_label.setText(f"{single_level_count} single level skills")
        self.multilevel_btn.setEnabled(multilevel_count > 0)
        if multilevel_count > 0:
            self.multilevel_btn.setText(f"📊 Multilevel Skills ({multilevel_count})")

    def open_multilevel_dialog(self):
        """Abre modal de skills multilevel"""
        site_type = self.current_problem.site_type if self.current_problem else 'main'
        dialog = MultilevelSkillDialog(self, site_type)
        dialog.exec()
        
        # Atualizar após fechar
        self.filter_items()

    def filter_items(self):
        """Filtra ambas as listas de itens"""
        text_filter = self.filter_edit.text().lower()
        type_filter = self.filter_combo.currentText()
        
        # Filtrar box problems
        self.filtered_box_problems = []
        for problem in self.box_problems:
            if text_filter and text_filter not in problem['item_id'].lower():
                continue
            
            # Filtro de tipo
            if type_filter == "No Scraper Data" and problem['has_scraper_data']:
                continue
            elif type_filter == "No XML" and problem['has_xml']:
                continue
            elif type_filter == "XML Incorrect" and (problem['has_xml'] and problem['xml_correct']):
                continue
            elif type_filter == "Has Data" and not (problem['has_scraper_data'] and problem['has_xml']):
                continue
                
            self.filtered_box_problems.append(problem)

        # Filtrar skill problems
        self.filtered_skill_problems = []
        for problem in self.skill_problems:
            if text_filter and text_filter not in problem['item_id'].lower():
                continue
            
            # Filtro de tipo
            if type_filter == "No Scraper Data" and problem['has_scraper_data']:
                continue
            elif type_filter == "No XML" and problem['has_xml']:
                continue
            elif type_filter == "XML Incorrect" and (not problem['has_xml'] or problem['xml_correct']):
                continue
            elif type_filter == "Has Data" and not (problem['has_scraper_data'] and problem['has_xml']):
                continue
                
            self.filtered_skill_problems.append(problem)
            self.filtered_problems = self.filtered_box_problems + self.filtered_skill_problems
        
        self.populate_box_items_list()
        self.populate_skills_list()
            
    def on_box_item_selected(self, item):
        raw_data = item.data(Qt.ItemDataRole.UserRole)
        
        # ✅ CONVERTE DICIONÁRIO PARA OBJETO PROBLEM MODEL
        self.current_problem = ProblemModel(
            item_id=raw_data['item_id'],
            skill_id=raw_data.get('skill_id'),
            site_type=raw_data['site_type'],
            issues=raw_data.get('issues', []),
            scraper_data=raw_data.get('scraper_data'),
            xml_data=raw_data.get('xml_data'),
            needs_fix=raw_data.get('needs_fix', True),
            validation_status=raw_data.get('validation_status', 'INVALID') 
        )

        # Helpers do objeto
        has_skills = self.current_problem.has_skills
        
        if has_skills:
            self.editor_tabs.setTabEnabled(1, True)
        else:
            self.editor_tabs.setTabEnabled(1, False)
            self.editor_tabs.setCurrentIndex(0) 

        self.update_selected_item_display()
        
        current_row = self.box_items_list.currentRow()
        self.prev_btn.setEnabled(current_row > 0)
        self.next_btn.setEnabled(current_row < self.box_items_list.count() - 1)
        self.skills_list.clearSelection()

    def on_skill_item_selected(self, item):
        self.current_selection_type = "skill"
        skill_data = item.data(Qt.ItemDataRole.UserRole)
        
        # Extrai raw problem
        raw_data = skill_data['problem']
        
        # ✅ CONVERTE PARA OBJETO
        self.current_problem = ProblemModel(
            item_id=raw_data['item_id'],
            skill_id=raw_data.get('skill_id'),
            site_type=raw_data['site_type'],
            issues=raw_data.get('issues', []),
            scraper_data=raw_data.get('scraper_data'),
            xml_data=raw_data.get('xml_data'),
            needs_fix=raw_data.get('needs_fix', True),
            validation_status=raw_data.get('validation_status', 'INVALID') 
        )
        
        self.current_skill_data = skill_data
        
        self.editor_tabs.setTabEnabled(1, True)
        self.editor_tabs.setCurrentIndex(1)
        
        self.save_skill_btn.setEnabled(True)
        self.auto_fix_skill_btn.setEnabled(True)
        self.save_item_btn.setEnabled(True)
        self.auto_fix_item_btn.setEnabled(True)
        
        current_row = self.skills_list.currentRow()
        self.prev_btn.setEnabled(current_row > 0)
        self.next_btn.setEnabled(current_row < self.skills_list.count() - 1)
        
        self.update_skill_single_level_display(
            skill_data['skill_id'], 
            skill_data['skill_level'], 
            raw_data, 
            skill_data['site_type']
        )
        self.box_items_list.clearSelection()

    def update_skill_single_level_display(self, skill_id: str, skill_level: int, problem: dict, site_type: str):
        scraper_data = problem.get('scraper_data', {})
        item_id = problem['item_id']
        
        skill_name = self.skill_handler.get_skill_name_from_skill_id(skill_id, site_type)
        item_name = self.skill_handler.get_item_name_from_item_id(item_id, site_type)
        
        info_lines = [
            f"Skill ID: {skill_id}",
            f"Skill Name: {skill_name}",
            f"Level: {skill_level}",
            f"Item ID: {item_id}",
            f"Item Name: {item_name}",
            f"Site: {site_type.upper()}",
            ""
        ]
        
        if scraper_data:
            box_data = scraper_data.get('box_data', {})
            g = len(box_data.get('guaranteed_items', []))
            r = len(box_data.get('random_items', []))
            p = len(box_data.get('possible_items', []))
            info_lines.append(f"Box Contents:")
            info_lines.append(f"  → {g} guaranteed, {r} random, {p} possible")
        
        self.info_text.setText('\n'.join(info_lines))
        
        if scraper_data:
            self.scraper_text.setText(self.format_scraper_summary(scraper_data))
        else:
            self.scraper_text.setText("No scraper data")
        
        self.load_skill_xml_single_level(skill_id, skill_level, scraper_data, site_type)
        self.load_item_xml_into_editor()

    def load_skill_xml_single_level(self, skill_id: str, skill_level: int, scraper_data: dict, site_type: str):
        skill_xml_data = self.xml_handler.load_skill_xml_data(skill_id, site_type)
        if not skill_xml_data:
            self.skill_xml_editor.setText(f"\n")
            return
        
        skill_xml = skill_xml_data['content']
        lines = skill_xml.split('\n')
        cleaned = [line[1:] if line.startswith('\t') else line for line in lines]
        skill_xml = '\n'.join(cleaned)
        skill_xml = self.xml_handler.fix_self_closing_tags(skill_xml)
        self.skill_xml_editor.setText(skill_xml)

    def format_scraper_summary(self, scraper_data):
        lines = []
        scraping_info = scraper_data.get('scraping_info', {})
        lines.append(f"Type: {scraping_info.get('item_type', 'Unknown')}")
        lines.append(f"Extractable: {scraping_info.get('is_extractable', False)}")
        lines.append(f"Has Skills: {scraping_info.get('has_skills', False)}")
        
        skill_id = self.scraper_handler.get_skill_id(scraper_data)
        if skill_id:
            lines.append(f"Skill ID: {skill_id}")
        
        box_data = scraper_data.get('box_data', {})
        lines.append("\nBox Contents:")
        guaranteed = box_data.get('guaranteed_items', [])
        random_items = box_data.get('random_items', [])
        possible = box_data.get('possible_items', [])
        
        lines.append(f"  Guaranteed: {len(guaranteed)} items")
        lines.append(f"  Random: {len(random_items)} items")
        lines.append(f"  Possible: {len(possible)} items")
        
        if guaranteed:
            lines.append("\n  Example Guaranteed Items:")
            for item in guaranteed[:3]:
                lines.append(f"    • {item['name']} x{item['count']}")
        return '\n'.join(lines)
    
    def save_item_xml(self):
        """Salva item usando atributos do ProblemModel"""
        if not self.current_problem or not self.current_problem.has_scraper_data:
            QMessageBox.warning(self, "Save Error", "No data to save")
            return
        
        try:
            item_id = self.current_problem.item_id
            site_type = self.current_problem.site_type
            scraper_data = self.current_problem.scraper_data
            
            reply = QMessageBox.question(
                self, 
                'Confirm Save', 
                f"Save changes to item {item_id} ({site_type.upper()})?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
            
            # Cálculo de arquivo
            block_num = int(item_id) // 100
            block_start = block_num * 100
            block_end = block_start + 99
            filename = f"{block_start:05d}-{block_end:05d}.xml"
            
            if site_type == "essence":
                output_dir = Path("output_items_essence")
                xml_file = Path(f"items_essence/{filename}")
            else:
                output_dir = Path("output_items_main")
                xml_file = Path(f"items_main/{filename}")
            
            output_dir.mkdir(exist_ok=True)
            output_file = output_dir / filename
            file_to_load = output_file if output_file.exists() else xml_file
            
            # Carregar e encontrar item
            parser = etree.XMLParser(remove_blank_text=False, remove_comments=False)
            tree = etree.parse(str(file_to_load), parser)
            root = tree.getroot()
            items = root.xpath(f".//item[@id='{item_id}'][@name][@type]")
            
            if not items:
                QMessageBox.warning(self, "Save Error", f"Item {item_id} not found in XML")
                return
            
            item_elem = items[0] #type: ignore
            
            scraper_data = self.current_problem.scraper_data

            # ✅ USAR edit_item_inplace (existe no ItemHandler)
            self.item_handler.edit_item_inplace(item_elem, scraper_data, item_id, site_type) if scraper_data is not None else ""
            
            # Skills
            skill_id = self.current_problem.get_skill_id()
            if self.current_problem.has_skills and skill_id:
                try:
                    fixed_skill = self.skill_handler.generate_fixed_skill_xml(
                        skill_id, 
                        scraper_data, 
                        site_type
                    ) if scraper_data is not None else ""
                    
                    if fixed_skill:
                        self.xml_handler.save_skill_xml_internal(
                            skill_id, 
                            fixed_skill, 
                            site_type, 
                            skip_confirmation=True
                        )
                        print(f"✅ Skill {skill_id} salva automaticamente")
                except Exception as e:
                    print(f"⚠️ Erro salvando skill: {e}")
            
            # Salvar Arquivo
            tree.write(
                str(output_file), 
                encoding='utf-8', 
                xml_declaration=True, 
                pretty_print=False
            )
            
            # Fix self-closing tags
            with open(output_file, 'r', encoding='utf-8') as f:
                content = f.read()
            content = re.sub(r'(?<!\s)/>', ' />', content)
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            QMessageBox.information(
                self, 
                "Success", 
                f"✓ XML saved successfully!\n\nSite: {site_type.upper()}\nOutput: {output_file}"
            )
            
            # Remove da lista de problemas
            # Precisa remover do dict original, não do ProblemModel
            for i, prob in enumerate(self.problems):
                if prob['item_id'] == item_id and prob['site_type'] == site_type:
                    self.problems.pop(i)
                    break
            
            for i, prob in enumerate(self.box_problems):
                if prob['item_id'] == item_id and prob['site_type'] == site_type:
                    self.box_problems.pop(i)
                    break
            
            # Atualizar UI
            self.filter_items()
            
            if self.box_items_list.count() > 0:
                self.box_items_list.setCurrentRow(0)
            else:
                self.clear_editor()
            
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Error saving:\n{str(e)}")
            import traceback
            traceback.print_exc()

    def edit_item_inplace_lxml(self, item_elem, scraper_data: dict, item_id: str, site_type: str = "main"):
        """
        Edita item in-place usando LXML
        Preserva formatação original COMPLETAMENTE
        """
        scraping_info = scraper_data.get('scraping_info', {})
        item_type = scraping_info.get('item_type', '')
        has_skills = scraping_info.get('has_skills', False)
        skill_id = self.scraper_handler.get_skill_id(scraper_data)

        print(f"  📝 Editando item {item_id} in-place...")

        # Determinar action correta
        if has_skills and skill_id:
            correct_action = item_type  # SKILL_REDUCE*
        else:
            correct_action = 'PEEL'

        # Atualizar default_action
        self.skill_handler._update_or_add_set_tag_lxml(item_elem, 'default_action', correct_action)
        
        # Atualizar handler
        if has_skills and skill_id:
            self.skill_handler._update_or_add_set_tag_lxml(item_elem, 'handler', 'ItemSkills')
            
            # Guardar tail do capsuled_items antes de remover
            capsuled_tail = '\n\t'
            for capsuled in item_elem.xpath('./capsuled_items'):
                if capsuled.tail:
                    capsuled_tail = capsuled.tail
                item_elem.remove(capsuled)
            
            # Remover extractableCount
            for tag in item_elem.xpath("./set[@name='extractableCountMin']"):
                item_elem.remove(tag)
            for tag in item_elem.xpath("./set[@name='extractableCountMax']"):
                item_elem.remove(tag)
            
            # Atualizar skills COM TAIL ORIGINAL
            self.skill_handler._update_or_create_skills_lxml(item_elem, skill_id, site_type, capsuled_tail)
            
        else:
            self.skill_handler._update_or_add_set_tag_lxml(item_elem, 'handler', 'ExtractableItems')
            
            # Guardar tail do skills antes de remover
            skills_tail = '\n\t'
            for skills in item_elem.xpath('./skills'):
                if skills.tail:
                    skills_tail = skills.tail
                item_elem.remove(skills)
            
            # Atualizar capsuled_items COM TAIL ORIGINAL
            box_data = scraper_data.get('box_data', {})
            self.item_handler._update_capsuled_items_lxml(item_elem, box_data, item_id, skills_tail)
            
            # Atualizar extractableCount
            self.item_handler._update_extractable_count_lxml(item_elem, box_data)
        
        print(f"  ✅ Item {item_id} editado com sucesso")

    def auto_fix_item(self):
        if not self.current_problem or not self.current_problem.has_scraper_data:
            QMessageBox.warning(self, "Auto-Fix Error", "Need scraper data")
            return

        try:
            # ✅ PASSA OS PARÂMETROS CORRETOS
            scraper_data = self.current_problem.scraper_data
            xml_data = self.current_problem.xml_data
            if scraper_data and xml_data is not None and isinstance(scraper_data, dict):
                fixed_xml = self.item_handler.generate_fixed_xml(
                    item_id=self.current_problem.item_id,
                    scraper_data=scraper_data,
                    site_type=self.current_problem.site_type,
                    xml_data=xml_data,  # ← IMPORTANTE!
                )
            
            if fixed_xml:
                # Mostra no editor (remove 1 tab)
                lines = fixed_xml.split('\n')
                cleaned = [line[1:] if line.startswith('\t') else line for line in lines]
                self.item_xml_editor.setText('\n'.join(cleaned))
                
                # Salva skill se necessário
                if self.current_problem.has_skills:
                    skill_id = self.current_problem.get_skill_id()
                    scraper_data = self.current_problem.scraper_data
                    site_type = self.current_problem.site_type
                    
                    try:
                        skill_xml = self.skill_handler.generate_fixed_skill_xml(
                            skill_id, 
                            scraper_data, 
                            site_type
                        ) if skill_id and scraper_data is not None else ""
                        
                        if skill_xml:
                            self.xml_handler.save_skill_xml_internal(
                                skill_id, 
                                skill_xml, 
                                site_type, 
                                skip_confirmation=True
                            ) if skill_id is not None else ""

                            QMessageBox.information(
                                self, 
                                "Auto-Fix", 
                                "✓ Item XML and Skill XML generated!\n\nReview and click Save."
                            )
                        else:
                            QMessageBox.information(
                                self, 
                                "Auto-Fix", 
                                "✓ Item XML generated!\n\nBut couldn't generate skill XML."
                            )
                    except Exception as e:
                        print(f"Erro ao gerar skill: {e}")
                        QMessageBox.information(
                            self, 
                            "Auto-Fix", 
                            "✓ Item XML generated!\n\nSkill generation failed."
                        )
                else:
                    QMessageBox.information(
                        self, 
                        "Auto-Fix", 
                        "✓ Item XML generated!\n\nReview and click Save."
                    )
            else:
                QMessageBox.warning(self, "Auto-Fix Error", "Could not generate XML")
                
        except Exception as e:
            QMessageBox.warning(self, "Auto-Fix Error", f"Error: {e}")
            import traceback
            traceback.print_exc()

    def auto_fix_skill(self):
        if not hasattr(self, 'current_skill_data'): return
        
        skill_data = self.current_skill_data
        skill_id = skill_data['skill_id']
        skill_level = skill_data['skill_level']
        site_type = skill_data['site_type']
        problem = skill_data['problem']
        scraper_data = problem.get('scraper_data')
        
        try:
            # Delegate to Skill Handler
            xml = self.skill_handler.generate_fixed_skill_xml_single_level(
                skill_id, skill_level, scraper_data, site_type
            )
            
            if xml:
                lines = xml.split('\n')
                cleaned = [line[1:] if line.startswith('\t') else line for line in lines]
                self.skill_xml_editor.setText('\n'.join(cleaned))
                QMessageBox.information(self, "Success", f"Skill {skill_id} fixed in editor.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"{e}")

    def save_skill_xml(self):
        if not hasattr(self, 'current_skill_data'): 
            return
        
        skill_data = self.current_skill_data
        skill_id = skill_data['skill_id']
        site_type = skill_data['site_type']
        
        # ✅ PEGAR XML DO EDITOR (como está!)
        xml_content = self.skill_xml_editor.toPlainText()
        
        # ✅ GARANTIR tail final (só isso!)
        if not xml_content.endswith('\n\t'):
            xml_content = xml_content.rstrip() + '\n\t'
        
        # ✅ MANDAR DIRETO (sem mexer!)
        self.xml_handler.save_skill_xml_internal(skill_id, xml_content, site_type)

    def clear_editor(self):
        self.info_text.clear()
        self.scraper_text.clear()
        self.item_xml_editor.clear()
        self.skill_xml_editor.clear()
        self.save_item_btn.setEnabled(False)
        self.save_skill_btn.setEnabled(False)
        self.auto_fix_item_btn.setEnabled(False)
        self.auto_fix_skill_btn.setEnabled(False)
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.current_problem = None

    def update_selected_item_display(self):
        """Atualiza display e DESABILITA botões se item OK"""
        if not self.current_problem:
            return
            
        scraper_data = self.current_problem.scraper_data
        needs_fix = self.current_problem.needs_fix if hasattr(self.current_problem, 'needs_fix') else True
        
        has_skills = False
        skill_id = None
        
        if scraper_data:
            scraping_info = scraper_data.get('scraping_info', {})
            has_skills = scraping_info.get('has_skills', False)
            skill_id = self.scraper_handler.get_skill_id(scraper_data)
        
        # ✅ DESABILITA BOTÕES SE ITEM OK
        if not needs_fix:
            self.save_item_btn.setEnabled(False)
            self.auto_fix_item_btn.setEnabled(False)
            self.save_skill_btn.setEnabled(False)
            self.auto_fix_skill_btn.setEnabled(False)
        else:
            self.save_item_btn.setEnabled(True)
            self.auto_fix_item_btn.setEnabled(scraper_data is not None)
            
            has_skill_to_edit = has_skills and skill_id is not None and scraper_data is not None
            self.save_skill_btn.setEnabled(has_skill_to_edit)
            self.auto_fix_skill_btn.setEnabled(has_skill_to_edit)
        
        # Configurar tabs
        if has_skills and skill_id:
            self.editor_tabs.setTabEnabled(1, True)
            self.skill_tab.setEnabled(True)
        else:
            self.editor_tabs.setTabEnabled(1, False)
            self.skill_tab.setEnabled(False)
            self.editor_tabs.setCurrentIndex(0)
        
        # Atualizar informações
        info_lines = [
            f"Item ID: {self.current_problem.item_id}",
            f"Type: {'Skill Item' if self.current_problem.has_skills else 'Box Item'}",
            f"Site: {self.current_problem.site_type.upper()}",
            f"Status: {'❌ NEEDS FIX' if needs_fix else '✅ OK'}",
            f"Has Skills: {'✓' if self.current_problem.has_skills else '✗'}",
            f"Skill ID: {self.current_problem.get_skill_id() or 'N/A'}",
            f"Has Scraper Data: {'✓' if self.current_problem.has_scraper_data else '✗'}",
            f"Has XML: {'✓' if self.current_problem.has_xml else '✗'}",
            "",
            "Issues:",
        ]
        info_lines.extend([f"  • {issue}" for issue in self.current_problem.issues])
        
        self.info_text.setText('\n'.join(info_lines))
        
        if scraper_data:
            scraper_summary = self.format_scraper_summary(scraper_data)
            self.scraper_text.setText(scraper_summary)
        else:
            self.scraper_text.setText("❌ No scraper data available")
        
        self.load_item_xml_into_editor()
        if has_skills and skill_id and scraper_data is not None:
            self.load_skill_xml_into_editor(skill_id, scraper_data)
        else:
            self.skill_xml_editor.setText("<!-- No skill to edit -->")

        self.skill_tab.setEnabled(True)

    def load_item_xml_into_editor(self):
        """Carrega o XML do item no editor de item (MÉTODO NOVO)"""
        if not self.current_problem or not self.current_problem.xml_data:
            self.item_xml_editor.setText("<!-- Item XML not available -->")
            return
        
        try:
            xml_file = Path(self.current_problem.xml_data['file'])
            item_id = self.current_problem.get_item_id()
            
            with open(xml_file, 'r', encoding='utf-8') as f:
                full_xml = f.read()
            
            import re
            pattern = rf'(<item[^>]*\sid="{item_id}"[^>]*>.*?</item>)'
            match = re.search(pattern, full_xml, re.DOTALL)
            
            if match:
                item_xml = match.group(1)
                item_xml = re.sub(r'\s+xmlns:xsi="[^"]*"', '', item_xml)
                item_xml = re.sub(r'\s+xmlns="[^"]*"', '', item_xml)
                
                # Remover 1 tab de cada linha
                lines = item_xml.split('\n')
                cleaned_lines = []
                for line in lines:
                    if line.startswith('\t'):
                        cleaned_lines.append(line[1:])
                    else:
                        cleaned_lines.append(line)
                item_xml = '\n'.join(cleaned_lines)
                item_xml = re.sub(r'(?<!\s)/>', ' />', item_xml)
                self.item_xml_editor.setText(item_xml)
            else:
                self.item_xml_editor.setText(f"<!-- Item {item_id} not found -->")
                
        except Exception as e:
            self.item_xml_editor.setText(f"<!-- Error loading item XML: {e} -->")

    def load_skill_xml_into_editor(self, skill_id: str, scraper_data: dict):
        """Carrega o XML da skill no editor de skill SEM modificar"""
        try:
            site_type = self.current_problem.site_type.upper() if self.current_problem is not None else False
            
            # ✅ SEMPRE carregar do arquivo existente (não gerar automaticamente)
            skill_xml_data = self.xml_handler.load_skill_xml_data(skill_id, site_type) if site_type is not False else self.xml_handler.load_skill_xml_data(skill_id, 'default_site')
            
            if skill_xml_data:
                skill_xml = skill_xml_data['content'] # ✅ Carrega como está
            else:
                # ❌ Não encontrado - mostrar placeholder ao invés de gerar
                self.skill_xml_editor.setText(f"<!-- Skill {skill_id} not found in {site_type.upper()} -->\n<!-- Click 'Auto-Fix Skill' to generate -->") if site_type is not False else True
                return
            
            # Remover tabs para visualização (o namespace já foi removido)
            lines = skill_xml.split('\n')
            cleaned_lines = []
            for line in lines:
                if line.startswith('\t'):
                    cleaned_lines.append(line[1:])
                else:
                    cleaned_lines.append(line)
            skill_xml = '\n'.join(cleaned_lines)
            skill_xml = re.sub(r'(?<!\s)/>', ' />', skill_xml)                
            self.skill_xml_editor.setText(skill_xml)
                
        except Exception as e:
            self.skill_xml_editor.setText(f"<!-- Error loading skill XML: {e} -->\n<!-- Click 'Auto-Fix Skill' to generate -->")

    def format_item_xml(self):
        txt = self.item_xml_editor.toPlainText()
        self.item_xml_editor.setText(self.xml_handler.format_xml_string(txt))

    def format_skill_xml(self):
        txt = self.skill_xml_editor.toPlainText()
        self.skill_xml_editor.setText(self.xml_handler.format_xml_string(txt))

    def validate_item_xml(self):
        try:
            etree.fromstring(self.item_xml_editor.toPlainText())
            QMessageBox.information(self, "Valid", "XML Valid")
        except Exception as e:
            QMessageBox.warning(self, "Invalid", str(e))

    def validate_skill_xml(self):
        try:
            etree.fromstring(self.skill_xml_editor.toPlainText())
            QMessageBox.information(self, "Valid", "XML Valid")
        except Exception as e:
            QMessageBox.warning(self, "Invalid", str(e))

    def previous_item(self):
        curr = self.box_items_list.currentRow()
        if curr > 0: self.box_items_list.setCurrentRow(curr - 1)

    def next_item(self):
        curr = self.box_items_list.currentRow()
        if curr < self.box_items_list.count() - 1: self.box_items_list.setCurrentRow(curr + 1)

    def export_problem_list(self):
        """Exporta lista de problemas para arquivo"""
        try:
            output_file = Path("problem_items_report.txt")
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write("ITEM BUILDER - PROBLEM ITEMS REPORT\n")
                f.write("=" * 80 + "\n\n")
                
                f.write(f"Total Problems Found: {len(self.problems)}\n")
                f.write(f"Currently Filtered: {len(self.filtered_problems)}\n\n")
                
                no_scraper = [p for p in self.problems if not p.get('has_scraper_data')]
                no_xml = [p for p in self.problems if not p.get('has_xml')]
                needs_fix = [p for p in self.problems if p.get('needs_fix', False)]
                
                f.write(f"No Scraper Data: {len(no_scraper)}\n")
                f.write(f"No XML: {len(no_xml)}\n")
                f.write(f"Needs Fix: {len(needs_fix)}\n\n")
                
                f.write("=" * 80 + "\n")
                f.write("DETAILED LIST\n")
                f.write("=" * 80 + "\n\n")
                
                for problem in self.problems:
                    f.write(f"Item ID: {problem['item_id']} ({problem['site_type']})\n")
                    f.write(f"Status: {problem.get('validation_status', 'UNKNOWN')}\n")
                    f.write(f"Issues ({len(problem['issues'])}):\n")
                    
                    for issue in problem['issues']:
                        f.write(f"  • {issue}\n")
                    f.write("\n")
            
            QMessageBox.information(
                self,
                "Export Complete",
                f"Problem list exported to:\n{output_file.absolute()}"
            )
            
        except Exception as e:
            QMessageBox.warning(self, "Export Error", f"Failed to export:\n{str(e)}")

    def auto_fix_all(self):

        # DEBUG
        print("=== AUTO-FIX ALL DEBUG ===")
        print(f"Total problems: {len(self.problems)}")
        print(f"Box problems: {len(self.box_problems)}")
        print(f"Skill problems: {len(self.skill_problems)}")
        print(f"Filtered problems: {len(self.filtered_problems)}")
        print(f"Filtered box problems: {len(self.filtered_box_problems)}")
        print(f"Filtered skill problems: {len(self.filtered_skill_problems)}")
        
        if self.filtered_problems:
            print("First filtered problem:", self.filtered_problems[0])
            print("Has scraper data:", self.filtered_problems[0].get('has_scraper_data'))
        print("=" * 50)
        
        fixable_items = [p for p in self.filtered_problems if p['has_scraper_data']]
        
        print(f"Fixable items count: {len(fixable_items)}")
        
        if not fixable_items:
            QMessageBox.information(self, "Auto-Fix All", "No items can be auto-fixed (need scraper data)")
            return
        
        reply = QMessageBox.question(
            self,
            'Confirm Auto-Fix All',
            f"This will attempt to auto-fix {len(fixable_items)} items.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.run_batch_auto_fix(fixable_items)
    
    def run_batch_auto_fix(self, items_to_fix):
        """Batch processing com LXML - com filtro multilevel"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(items_to_fix))

        # ✅ Carregar multilevel skills set (se não tiver sido carregado)
        if not hasattr(self, 'multilevel_skills_set'):
            self.multilevel_skills_set = set()
            if self.site_type == "main":
                json_filename = f"multilevel_skills_main.json"
                if os.path.exists(json_filename):
                    try:
                        with open(json_filename, 'r', encoding='utf-8') as f:
                            multilevel_data = json.load(f)
                            self.multilevel_skills_set = set(multilevel_data.keys())
                            print(f"✅ Carregadas {len(self.multilevel_skills_set)} skills multilevel para filtro")
                    except Exception as e:
                        print(f"⚠️ Erro ao carregar multilevel JSON: {e}")

        skill_errors = []
        
        # Agrupar por arquivo
        items_by_file = {}
        for problem in items_to_fix:
            if not problem.get('xml_data'):
                continue
            
            file_path = problem['xml_data']['file']
            if file_path not in items_by_file:
                items_by_file[file_path] = []
            items_by_file[file_path].append(problem)
        
        success_count = 0
        failed_count = 0
        skill_success = 0
        skill_failed = 0
        skill_skipped = 0
        
        # Processar cada arquivo
        for file_path, problems in items_by_file.items():
            print(f"\n{'='*80}")
            print(f"📄 Processando {Path(file_path).name} ({len(problems)} items)")
            print(f"{'='*80}")
            
            site_type = problems[0]['site_type']
            output_dir = Path("output_items_essence" if site_type == "essence" else "output_items_main")
            output_dir.mkdir(exist_ok=True)
            output_file = output_dir / Path(file_path).name
            
            file_to_load = output_file if output_file.exists() else file_path
            
            try:
                # ✅ CARREGAR COM LXML
                parser = etree.XMLParser(remove_blank_text=False, remove_comments=False)
                tree = etree.parse(str(file_to_load), parser)
                root = tree.getroot()
                
                # Processar cada item
                for i, problem in enumerate(problems, 1):
                    item_id = problem['item_id']
                    self.progress_bar.setValue(success_count + failed_count + 1)
                    self.status_label.setText(f"Processing {item_id} ({i}/{len(problems)})...")
                    
                    print(f"\n[{i}/{len(problems)}] Item {item_id}")
                    
                    try:
                        # Encontrar item
                        items = root.xpath(f".//item[@id='{item_id}'][@name][@type]")
                        if not items:
                            print(f"  ❌ Item não encontrado")
                            failed_count += 1
                            continue
                        
                        item_elem = items[0]

                        # Editar
                        self.edit_item_inplace_lxml(item_elem, problem['scraper_data'], item_id, site_type)
                        success_count += 1
                        
                        # Skill (COM FILTRO MULTILEVEL)
                        scraper_data = problem.get('scraper_data', {})
                        scraping_info = scraper_data.get('scraping_info', {})
                        if scraping_info.get('has_skills', False):
                            skill_id = self.scraper_handler.get_skill_id(scraper_data)
                            if skill_id:
                                # ✅ PULA skills que estão no JSON multilevel
                                if str(skill_id) in self.multilevel_skills_set:
                                    print(f"  ⏭️  Skill {skill_id} é MULTILEVEL (no JSON), PULANDO")
                                    skill_skipped += 1
                                    continue
                                
                                try:
                                    skill_level = scraper_data.get('skill_data', {}).get('skill_level', 1)
                                    print(f"  🔧 Processando skill {skill_id} (level {skill_level})...")
                                    
                                    fixed_skill = self.skill_handler.generate_fixed_skill_xml_single_level(
                                        skill_id, 
                                        skill_level,
                                        scraper_data,
                                        site_type
                                    )
                                    
                                    if fixed_skill:
                                        self.xml_handler.save_skill_xml_internal(
                                            skill_id, 
                                            fixed_skill, 
                                            site_type, 
                                            skip_confirmation=True
                                        )
                                        skill_success += 1
                                        print(f"    ✅ Skill {skill_id} salva")
                                    else:
                                        skill_failed += 1
                                        error_msg = f"Item {item_id} | Skill {skill_id} | Não gerou XML da skill"
                                        skill_errors.append(error_msg)
                                        print(f"    ❌ Não gerou XML da skill {skill_id}")
                                        
                                except Exception as e:
                                    skill_failed += 1
                                    error_msg = f"Item {item_id} | Skill {skill_id} | Erro: {str(e)}"
                                    skill_errors.append(error_msg)
                                    print(f"    ❌ Erro na skill {skill_id}: {e}")
                    
                    except Exception as e:
                        print(f"  ❌ Erro no item {item_id}: {e}")
                        failed_count += 1
                
                # ✅ SALVAR COM LXML (APÓS processar TODOS os itens)
                tree.write(
                    str(output_file),
                    encoding='utf-8',
                    xml_declaration=True,
                    pretty_print=False
                )

                with open(output_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                content = re.sub(r'(?<!\s)/>', ' />', content)
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(content)

                print(f"\n💾 Arquivo salvo: {output_file}")
                
            except Exception as e:
                print(f"❌ Erro no arquivo {file_path}: {e}")
                failed_count += len(problems)
        
        self.progress_bar.setVisible(False)
        self.filter_items()

        if skill_failed > 0:
            self.show_skill_errors_window(skill_errors)
        
        summary = [
            "BATCH AUTO-FIX COMPLETE:",
            "",
            f"Items: ✅ {success_count} | ❌ {failed_count}",
        ]
        
        if skill_success or skill_failed or skill_skipped:
            summary.append(f"Skills: ✅ {skill_success} | ❌ {skill_failed} | ⏭️ {skill_skipped} (multilevel)")
        
        QMessageBox.information(self, "Complete", "\n".join(summary))