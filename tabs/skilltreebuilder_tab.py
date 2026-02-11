from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                           QPushButton, QLabel, QProgressBar, QTextEdit,
                           QGroupBox, QGridLayout, QComboBox, QFrame,
                           QSpinBox, QCheckBox, QFileDialog, QTableWidget,
                           QTableWidgetItem, QAbstractItemView)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QTextCursor, QColor
from pathlib import Path
import time
import shutil
import xml.etree.ElementTree as ET

class SkillTreeBuilderTab(QWidget):
    builder_created = pyqtSignal(object, str)
    
    def __init__(self, config, database, skilltree_tab=None):
        super().__init__()
        self.config = config
        self.database = database
        self.builder_worker = None
        self.comparison_report = None
        self.skilltree_tab = skilltree_tab
        
        # Puxar mappings do SkillTreeTab se disponível
        if skilltree_tab:
            self.class_mapping_essence = skilltree_tab.class_mapping_essence
            self.class_mapping_main = skilltree_tab.class_mapping_main
        else:
            # Fallback se não houver acesso
            self.class_mapping_essence = {}
            self.class_mapping_main = {}
        
        self.class_mapping_actual = self.class_mapping_main
        self.site_type = "main"
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # --- SECTION 1: Configuration ---
        config_group = QGroupBox("Configuration")
        config_layout = QGridLayout(config_group)
        
        config_layout.addWidget(QLabel("Site:"), 0, 0)
        self.site_combo = QComboBox()
        self.site_combo.addItems(["main", "essence"])
        self.site_combo.currentTextChanged.connect(self.on_site_changed)
        config_layout.addWidget(self.site_combo, 0, 1)
        
        config_layout.addWidget(QLabel("Select Class:"), 1, 0)
        self.class_combo = QComboBox()
        config_layout.addWidget(self.class_combo, 1, 1)
        self.class_combo.currentTextChanged.connect(self.on_class_changed)

        self.info_label = QLabel("Ready to compare...")
        self.info_label.setStyleSheet("color: #777; font-family: 'Consolas'; font-size: 11px;")
        config_layout.addWidget(self.info_label, 2, 0, 1, 2)

        # --- SECTION 2: File Selection ---
        file_group = QGroupBox("Source Files")
        file_layout = QGridLayout(file_group)

        file_layout.addWidget(QLabel("JSON Path:"), 0, 0)
        self.json_input = QComboBox()
        self.json_input.setEditable(True)
        file_layout.addWidget(self.json_input, 0, 1)
        self.json_browse_btn = QPushButton("📁 Browse")
        self.json_browse_btn.clicked.connect(self.browse_json)
        file_layout.addWidget(self.json_browse_btn, 0, 2)

        file_layout.addWidget(QLabel("XML Path:"), 1, 0)
        self.xml_input = QComboBox()
        self.xml_input.setEditable(True)
        file_layout.addWidget(self.xml_input, 1, 1)
        self.xml_browse_btn = QPushButton("📁 Browse")
        self.xml_browse_btn.clicked.connect(self.browse_xml)
        file_layout.addWidget(self.xml_browse_btn, 1, 2)

        # --- SECTION 3: Options ---
        options_group = QGroupBox("Build Options")
        options_layout = QGridLayout(options_group)

        self.auto_merge_check = QCheckBox("Auto Merge Changes")
        self.auto_merge_check.setChecked(True)
        self.auto_merge_check.setToolTip("Automatically apply JSON changes to XML")
        options_layout.addWidget(self.auto_merge_check, 0, 0)

        self.create_backup_check = QCheckBox("Create Backup")
        self.create_backup_check.setChecked(True)
        self.create_backup_check.setToolTip("Backup original XML before changes")
        options_layout.addWidget(self.create_backup_check, 0, 1)

        options_layout.addWidget(QLabel("Max Workers:"), 1, 0)
        self.workers_spin = QSpinBox()
        self.workers_spin.setValue(5)
        self.workers_spin.setRange(1, 16)
        options_layout.addWidget(self.workers_spin, 1, 1)

        # --- SECTION 4: Actions ---
        action_layout = QHBoxLayout()
        self.compare_btn = QPushButton("🔍 Compare Only")
        self.build_btn = QPushButton("⚙️ Build XML")
        self.stop_btn = QPushButton("🛑 Stop")
        self.clear_log_btn = QPushButton("🗑️ Clear Log")
        self.stop_btn.setEnabled(False)
        
        action_layout.addWidget(self.compare_btn)
        action_layout.addWidget(self.build_btn)
        action_layout.addWidget(self.stop_btn)
        action_layout.addWidget(self.clear_log_btn)

        # --- SECTION 5: Progress ---
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.status_label = QLabel("Ready - XML Builder Idle")
        self.status_label.setStyleSheet("color: #555; font-weight: bold;")
        
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.status_label)

        # --- SECTION 6: Stats ---
        stats_group = QGroupBox("📊 Comparison Summary")
        stats_layout = QGridLayout(stats_group)
        
        self.total_skills_json = QLabel("JSON Skills: 0")
        self.total_skills_xml = QLabel("XML Skills: 0")
        self.skills_added = QLabel("Added: 0")
        self.skills_added.setStyleSheet("color: #4CAF50; font-weight: bold;")
        self.skills_removed = QLabel("Removed: 0")
        self.skills_removed.setStyleSheet("color: #F44336; font-weight: bold;")
        self.skills_modified = QLabel("Modified: 0")
        self.skills_modified.setStyleSheet("color: #FF9800; font-weight: bold;")
        
        stats_layout.addWidget(self.total_skills_json, 0, 0)
        stats_layout.addWidget(self.total_skills_xml, 0, 1)
        stats_layout.addWidget(self.skills_added, 1, 0)
        stats_layout.addWidget(self.skills_removed, 1, 1)
        stats_layout.addWidget(self.skills_modified, 2, 0)
        
        # --- SECTION 7: Tabs para Differences e Duplications ---
        from PyQt6.QtWidgets import QTabWidget
        
        self.details_tabs = QTabWidget()
        
        # TAB 1: Differences
        diff_group = QGroupBox("Detailed Differences")
        diff_layout = QVBoxLayout(diff_group)
        
        self.diffs_table = QTableWidget()
        self.diffs_table.setColumnCount(6)
        self.diffs_table.setHorizontalHeaderLabels([
            "Type", "Skill ID", "Level", "Field", "Old Value", "New Value"
        ])
        self.diffs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.diffs_table.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e1e;
                color: #dcdcdc;
                gridline-color: #444;
            }
            QHeaderView::section {
                background-color: #2d2d2d;
                color: #dcdcdc;
                padding: 5px;
                border: 1px solid #444;
            }
        """)
        diff_layout.addWidget(self.diffs_table)
        self.details_tabs.addTab(diff_group, "📊 Differences")
        
        # TAB 2: Duplications Report
        dup_group = QGroupBox("Duplicated Skills Report")
        dup_layout = QVBoxLayout(dup_group)
        
        dup_button_layout = QHBoxLayout()
        self.scan_duplications_btn = QPushButton("🔍 Scan for Duplications")
        self.scan_duplications_btn.clicked.connect(self.scan_duplications)
        self.export_dup_btn = QPushButton("💾 Export Report")
        self.export_dup_btn.setEnabled(False)
        self.export_dup_btn.clicked.connect(self.export_duplications_report)
        
        dup_button_layout.addWidget(self.scan_duplications_btn)
        dup_button_layout.addWidget(self.export_dup_btn)
        dup_layout.addLayout(dup_button_layout)
        
        self.dup_report_text = QTextEdit()
        self.dup_report_text.setReadOnly(True)
        self.dup_report_text.setMaximumHeight(300)
        self.dup_report_text.setStyleSheet("background-color: #1e1e1e; color: #dcdcdc; font-family: 'Consolas';")
        dup_layout.addWidget(self.dup_report_text)
        
        self.details_tabs.addTab(dup_group, "🔗 Duplications")

        # --- SECTION 8: Log ---
        log_group = QGroupBox("Execution Log")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setStyleSheet("background-color: #1e1e1e; color: #dcdcdc; font-family: 'Consolas';")
        log_layout.addWidget(self.log_text)
        
        # --- ASSEMBLE LAYOUT ---
        layout.addWidget(config_group)
        layout.addWidget(file_group)
        layout.addWidget(options_group)
        layout.addLayout(action_layout)
        layout.addWidget(progress_group)
        layout.addWidget(stats_group)
        layout.addWidget(self.details_tabs, 1)  # Tabs com Differences e Duplications
        layout.addWidget(log_group)
        
        self.setup_connections()
        self.update_class_dropdown()

    def setup_connections(self):
        self.compare_btn.clicked.connect(self.compare_xml)
        self.build_btn.clicked.connect(self.build_xml)
        self.stop_btn.clicked.connect(self.stop_building)
        self.clear_log_btn.clicked.connect(self.log_text.clear)

    def on_site_changed(self, site_type):
        self.site_type = site_type
        self.log(f"🌐 Site context: {site_type.upper()}")
        self.update_class_dropdown()

    def update_class_dropdown(self):
        self.class_combo.blockSignals(True)
        self.class_combo.clear()
        
        if self.site_type == "main":
            self.class_mapping_actual = self.class_mapping_main
        else:
            self.class_mapping_actual = self.class_mapping_essence
            
        self.class_combo.addItems(sorted(self.class_mapping_actual.keys()))
        self.class_combo.blockSignals(False)
        self.on_class_changed(self.class_combo.currentText())

    def on_class_changed(self, class_display_name):
        if not class_display_name:
            return
            
        mapping = self.class_mapping_actual.get(class_display_name)
        if mapping:
            self.current_slug = mapping['slug']
            self.current_folder = mapping['folder']
            self.current_xml = mapping['xml']
            
            # Pré-preenche os paths automático
            json_path = f"output_skilltree/{self.site_type}/{self.current_slug}/skills_deep_data.json"
            xml_path = f"skilltree/{self.site_type.title()}/{self.current_folder}/{self.current_xml}.xml"
            
            self.json_input.setCurrentText(json_path)
            self.xml_input.setCurrentText(xml_path)
            
            site_name = "Main" if self.site_type == "main" else "Essence"
            self.info_label.setText(
                f"Target -> Slug: {self.current_slug} | "
                f"Folder: {site_name}/{self.current_folder} | "
                f"XML: {self.current_xml}.xml"
            )

    def browse_json(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select JSON File", "", "JSON Files (*.json)"
        )
        if file_path:
            self.json_input.setCurrentText(file_path)

    def browse_xml(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select XML File", "", "XML Files (*.xml)"
        )
        if file_path:
            self.xml_input.setCurrentText(file_path)

    def compare_xml(self):
        json_path = self.json_input.currentText()
        xml_path = self.xml_input.currentText()
        
        if not json_path or not xml_path:
            self.log("❌ JSON and XML paths are required!")
            return

        self.log(f"--- Comparing JSON vs XML ---")
        self.log(f"JSON: {json_path}")
        self.log(f"XML:  {xml_path}")
        self.log("Processing...")

        try:
            from workers.skilltree_xml_builder import SkillTreeXMLBuilder
            
            self.builder_worker = SkillTreeXMLBuilder(
                json_path=json_path,
                xml_path=xml_path,
                auto_merge=False  # Apenas comparação, sem salvar
            )
            
            self.builder_worker.log_signal.connect(self.log)
            self.builder_worker.comparison_signal.connect(self.on_comparison_result)
            self.builder_worker.finished_signal.connect(lambda stats: self.on_compare_finished(stats, save=False))
            
            self.builder_worker.start()
            self.update_controls(True)
            self.progress_bar.setMaximum(0)
            
        except Exception as e:
            self.log(f"❌ Error: {str(e)}")

    def build_xml(self):
        json_path = self.json_input.currentText()
        xml_path = self.xml_input.currentText()
        
        if not json_path or not xml_path:
            self.log("❌ JSON and XML paths are required!")
            return

        self.log(f"--- Building XML ---")
        self.log(f"JSON: {json_path}")
        self.log(f"XML:  {xml_path}")

        try:
            from workers.skilltree_xml_builder import SkillTreeXMLBuilder
            
            self.builder_worker = SkillTreeXMLBuilder(
                json_path=json_path,
                xml_path=xml_path,
                auto_merge=False  # Preview first, aplicar depois
            )
            
            self.builder_worker.log_signal.connect(self.log)
            self.builder_worker.comparison_signal.connect(self.on_comparison_result)
            self.builder_worker.finished_signal.connect(lambda stats: self.on_compare_finished(stats, save=True))
            
            self.builder_worker.start()
            self.update_controls(True)
            self.progress_bar.setMaximum(0)
            
        except Exception as e:
            self.log(f"❌ Error: {str(e)}")

    def on_comparison_result(self, report):
        """Recebe relatório de comparação e atualiza a tabela"""
        self.comparison_report = report
        
        # Atualizar stats
        self.skills_added.setText(f"Added: {len(report.get('added', []))}")
        self.skills_removed.setText(f"Removed: {len(report.get('removed', []))}")
        self.skills_modified.setText(f"Modified: {len(report.get('modified', []))}")
        
        # Preencher tabela
        self.populate_diffs_table(report)

    def populate_diffs_table(self, report):
        """Popula a tabela com diferenças"""
        self.diffs_table.setRowCount(0)
        
        all_diffs = []
        
        # Adicionadas
        for item in report.get('added', []):
            all_diffs.append(('added', item))
        
        # Removidas
        for item in report.get('removed', []):
            all_diffs.append(('removed', item))
        
        # Modificadas
        for item in report.get('modified', []):
            all_diffs.append(('modified', item))
        
        self.diffs_table.setRowCount(len(all_diffs))
        
        for row, (change_type, item) in enumerate(all_diffs):
            # Type
            type_item = QTableWidgetItem(change_type.upper())
            if change_type == 'added':
                type_item.setForeground(QColor("#4CAF50"))
            elif change_type == 'removed':
                type_item.setForeground(QColor("#F44336"))
            else:
                type_item.setForeground(QColor("#FF9800"))
            
            self.diffs_table.setItem(row, 0, type_item)
            self.diffs_table.setItem(row, 1, QTableWidgetItem(str(item.get('skill_id', ''))))
            self.diffs_table.setItem(row, 2, QTableWidgetItem(str(item.get('level', ''))))
            self.diffs_table.setItem(row, 3, QTableWidgetItem(item.get('field', '')))
            self.diffs_table.setItem(row, 4, QTableWidgetItem(item.get('old', '')))
            self.diffs_table.setItem(row, 5, QTableWidgetItem(item.get('new', '')))

    def on_compare_finished(self, stats, save=False):
        """Chamado quando a comparação termina - mostra preview"""
        self.log(f"✅ Comparison Complete!")
        self.log(f"   JSON Skills: {stats['total_skills_json']}")
        self.log(f"   XML Skills: {stats['total_skills_xml']}")
        self.log(f"   Added: {stats['skills_added']} | Removed: {stats['skills_removed']} | Modified: {stats['skills_modified']}")
        self.log(f"   Duration: {stats['duration']:.2f}s")
        
        self.status_label.setText("Ready for preview")
        self.update_controls(False)
        self.progress_bar.setValue(self.progress_bar.maximum())
        
        # Mostrar preview window com XML modificado (TEXTO PURO)
        if self.builder_worker and hasattr(self.builder_worker, 'get_preview_text'):
            xml_text = self.builder_worker.get_preview_text()
            if xml_text:
                self.show_preview(xml_text, save=save)
            else:
                self.log("❌ No preview text available")
        else:
            self.log("❌ Builder worker not ready")
        
    def log(self, message):
        """Adiciona mensagem ao log"""
        self.log_text.append(f"[{time.strftime('%H:%M:%S')}] {message}")
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)
        # Auto-scroll
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def stop_building(self):
        if self.builder_worker:
            self.builder_worker.stop()
            self.log("🛑 Build cancelled...")

    def update_controls(self, building):
        self.compare_btn.setEnabled(not building)
        self.build_btn.setEnabled(not building)
        self.stop_btn.setEnabled(building)
        self.class_combo.setEnabled(not building)
        self.site_combo.setEnabled(not building)
    
    def scan_duplications(self):
        """Escaneia duplicações de skills"""
        self.log("🔍 Scanning for duplicated skills...")
        self.dup_report_text.setText("Scanning... please wait\n")
        
        try:
            from core.skilltree_duplication_detector import SkillTreeDuplicationDetector
            
            skilltree_path = "skilltree"
            detector = SkillTreeDuplicationDetector(skilltree_path, self.site_type)
            
            # Gerar relatório
            report = self._generate_dup_report(detector)
            
            self.dup_report_text.setPlainText(report)
            self.export_dup_btn.setEnabled(True)
            self.dup_detector = detector  # Armazenar pra export
            
            self.log(f"✅ Found {len(detector.duplicated_skills)} duplicated skills")
        
        except Exception as e:
            self.dup_report_text.setPlainText(f"❌ Error: {str(e)}")
            self.log(f"❌ Error scanning duplications: {str(e)}")
    
    def _generate_dup_report(self, detector) -> str:
        """Gera texto formatado do relatório de duplicações"""
        lines = []
        
        lines.append("=" * 80)
        lines.append(f"🔍 SKILLTREE DUPLICATION REPORT - {self.site_type.upper()}")
        lines.append("=" * 80)
        lines.append("")
        
        # Resumo
        lines.append("📊 SUMMARY")
        lines.append(f"  Total files scanned: {detector.total_files}")
        lines.append(f"  Total unique skills: {detector.total_unique_skills}")
        lines.append(f"  Duplicated skills: {len(detector.duplicated_skills)}")
        lines.append("")
        
        # Listar arquivos
        lines.append("📁 FILES SCANNED")
        for filename in sorted(set(f for files in detector.skill_files.values() for f in files)):
            count = sum(1 for files in detector.skill_files.values() if filename in files)
            lines.append(f"  {filename:<40} ({count} skills)")
        lines.append("")
        
        # Detalhar cada skill duplicada
        lines.append("🔗 DUPLICATED SKILLS (showing top 30)")
        lines.append("-" * 80)
        
        duplicated_sorted = sorted(
            detector.skill_files.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )
        
        count = 0
        for skill_key, files in duplicated_sorted:
            if len(files) > 1 and count < 30:
                skill_id, skill_level = skill_key.rsplit('_', 1)
                
                # Pegar info da skill
                skill_names = set()
                for filename in files:
                    for skill_info in detector.skills_by_file[skill_key][filename]:
                        skill_names.add(skill_info['skill_name'])
                
                skill_name = list(skill_names)[0] if skill_names else "Unknown"
                
                lines.append(f"\n  ID: {skill_id} | Lv: {skill_level} | Name: {skill_name}")
                lines.append(f"  Files ({len(files)}):")
                
                for filename in sorted(files):
                    lines.append(f"    ✓ {filename}")
                
                count += 1
        
        if len(detector.duplicated_skills) > 30:
            lines.append(f"\n... and {len(detector.duplicated_skills) - 30} more duplicated skills")
        
        lines.append("\n" + "=" * 80)
        
        return '\n'.join(lines)
    
    def export_duplications_report(self):
        """Exporta relatório de duplicações"""
        if not hasattr(self, 'dup_detector'):
            self.log("❌ No duplication scan data available")
            return
        
        try:
            filepath = Path("skilltree_duplications_report.txt")
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self.dup_report_text.toPlainText())
            
            self.log(f"✅ Report exported to: {filepath}")
            
            # Também exportar JSON
            json_path = Path("skilltree_duplications.json")
            self.dup_detector.export_json(str(json_path))
            self.log(f"✅ JSON exported to: {json_path}")
        
        except Exception as e:
            self.log(f"❌ Error exporting report: {str(e)}")

    def show_preview(self, xml_text, save=False):
        """Abre janela de preview do XML (agora recebe texto puro)"""
        try:
            from utils.xml_preview_window import XMLPreviewWindow
            
            # Passar texto puro (remove is_text=True)
            self.preview_window = XMLPreviewWindow(xml_text, parent=self)
            self.preview_window.should_save = save  # Flag pra saber se vai salvar
            self.preview_window.apply_signal.connect(self.on_preview_apply)
            self.preview_window.show()
            
        except Exception as e:
            self.log(f"❌ Error opening preview: {str(e)}")
            import traceback
            self.log(traceback.format_exc())
    
    def on_preview_apply(self):
        """Chamado quando o usuário clica em Apply no preview"""
        if not self.builder_worker:
            self.log("❌ No builder worker available")
            return
        
        should_save = getattr(self.preview_window, 'should_save', False)
        
        if should_save and self.create_backup_check.isChecked():
            xml_path = Path(self.xml_input.currentText())
            backup_path = xml_path.parent / f"{xml_path.stem}_backup_{int(time.time())}.xml"
            shutil.copy(xml_path, backup_path)
            self.log(f"📦 Backup created: {backup_path}")
        
        if should_save:
            self.log("\n✅ Saving XML changes...")
            # Pegar texto editado do preview (com comentários)
            edited_xml = self.preview_window.get_modified_xml()
            self.builder_worker.save_xml(edited_xml)
            self.log("✅ XML saved successfully!")
            self.status_label.setText("✅ Changes applied and saved!")
        else:
            self.log("✅ Preview closed - no changes applied")