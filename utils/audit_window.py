from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                           QTableWidgetItem, QPushButton, QLabel, QComboBox,
                           QMessageBox, QHeaderView, QTextEdit, QGroupBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
import json
from pathlib import Path
from datetime import datetime

class AuditWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.audit_entries = []
        self.setup_ui()
        
    def setup_ui(self):
        self.setWindowTitle("🔍 Auditoria em Tempo Real")
        self.setGeometry(200, 200, 1200, 700)
        
        layout = QVBoxLayout(self)
        
        # ===== CONTROLES SUPERIORES =====
        controls_layout = QHBoxLayout()
        
        # Filtros
        filters_layout = QHBoxLayout()
        filters_layout.addWidget(QLabel("Filtrar:"))
        
        self.status_filter = QComboBox()
        self.status_filter.addItems([
            "Todos", "Consistentes", "Inconsistentes", "Faltando", "Extraíveis", "Não Extraíveis"
        ])
        self.status_filter.currentTextChanged.connect(self.apply_filters)
        filters_layout.addWidget(self.status_filter)
        
        self.site_filter = QComboBox()
        self.site_filter.addItems(["Todos", "Main", "Essence", "SkillTree"])
        self.site_filter.currentTextChanged.connect(self.apply_filters)
        filters_layout.addWidget(self.site_filter)
        
        controls_layout.addLayout(filters_layout)
        
        # Botões de ação
        self.export_btn = QPushButton("💾 Exportar Auditoria")
        self.export_btn.clicked.connect(self.export_audit)
        controls_layout.addWidget(self.export_btn)
        
        self.clear_btn = QPushButton("🗑️ Limpar")
        self.clear_btn.clicked.connect(self.clear_audit)
        controls_layout.addWidget(self.clear_btn)
        
        controls_layout.addStretch()
        
        # Estatísticas
        self.stats_label = QLabel("Processados: 0 | Consistentes: 0 | Inconsistentes: 0 | Faltando: 0")
        controls_layout.addWidget(self.stats_label)
        
        layout.addLayout(controls_layout)
        
        # ===== TABELA DE AUDITORIA =====
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "ID/Class", "Tipo", "DAT/Source", "SITE", "EXPECTED", "XML", "STATUS", "Info"
        ])
        
        # Ajustar largura das colunas
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # ID
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Tipo
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # DAT
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # SITE
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # EXPECTED
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # XML
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # STATUS
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)  # Info
        
        layout.addWidget(self.table)
        
        # ===== LOG DETALHADO =====
        log_group = QGroupBox("Detalhes da Auditoria")
        log_layout = QVBoxLayout(log_group)
        
        self.details_text = QTextEdit()
        self.details_text.setMaximumHeight(150)
        self.details_text.setReadOnly(True)
        log_layout.addWidget(self.details_text)
        
        layout.addWidget(log_group)
        
        # Conectar seleção da tabela
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
    
    def add_audit_entry(self, audit_data):
        """Adiciona entrada de auditoria em tempo real (items OU skilltree)"""
        # Detectar tipo de auditoria
        entry_type = self.detect_audit_type(audit_data)
        audit_data['_audit_type'] = entry_type
        
        self.audit_entries.append(audit_data)
        self.update_table()
        self.update_stats()
        
        # Salvar em arquivo automaticamente
        self.save_to_audit_file(audit_data)
    
    def detect_audit_type(self, audit_data):
        """Detecta se é auditoria de item ou skilltree"""
        if 'item_id' in audit_data:
            return 'item'
        elif 'class_slug' in audit_data:
            return 'skilltree'
        else:
            return 'unknown'
    
    def update_table(self):
        """Atualiza a tabela com os dados filtrados"""
        filtered_entries = self.get_filtered_entries()
        
        self.table.setRowCount(len(filtered_entries))
        
        for row, entry in enumerate(filtered_entries):
            entry_type = entry.get('_audit_type', 'item')
            
            if entry_type == 'item':
                self.populate_item_row(row, entry)
            elif entry_type == 'skilltree':
                self.populate_skilltree_row(row, entry)
        
        # Scroll para baixo
        if filtered_entries:
            self.table.scrollToBottom()
    
    def populate_item_row(self, row, entry):
        """Popula linha com dados de item"""
        # Item ID
        self.table.setItem(row, 0, QTableWidgetItem(entry['item_id']))
        
        # Tipo
        self.table.setItem(row, 1, QTableWidgetItem(entry['site_type'].upper()))
        
        # DAT Action
        self.table.setItem(row, 2, QTableWidgetItem(entry['dat_action']))
        
        # SITE Action
        self.table.setItem(row, 3, QTableWidgetItem(entry['site_action']))
        
        # EXPECTED Action
        self.table.setItem(row, 4, QTableWidgetItem(entry['expected_action']))
        
        # XML Action
        xml_text = entry['xml_action'] if entry['xml_action'] else "NONE"
        self.table.setItem(row, 5, QTableWidgetItem(xml_text))
        
        # STATUS
        status_item = QTableWidgetItem(entry['status'])
        self.color_status_cell(status_item, entry['status'])
        self.table.setItem(row, 6, status_item)
        
        # Info
        extraible_text = "✅ Extraível" if entry['is_extractable'] else "❌ Não Ext."
        self.table.setItem(row, 7, QTableWidgetItem(extraible_text))
    
    def populate_skilltree_row(self, row, entry):
        """Popula linha com dados de skilltree"""
        # Class Slug
        self.table.setItem(row, 0, QTableWidgetItem(entry.get('class_slug', 'N/A')))
        
        # Tipo
        type_text = f"SKILLTREE-{entry.get('site_type', '').upper()}"
        self.table.setItem(row, 1, QTableWidgetItem(type_text))
        
        # Source (XML Class)
        self.table.setItem(row, 2, QTableWidgetItem(entry.get('xml_class_name', 'N/A')))
        
        # Site Total
        site_total = entry.get('site_total_skills', 0)
        self.table.setItem(row, 3, QTableWidgetItem(str(site_total)))
        
        # Expected (vazio por enquanto - builder vai preencher)
        self.table.setItem(row, 4, QTableWidgetItem("-"))
        
        # XML Total
        xml_total = entry.get('xml_total_skills', 0)
        self.table.setItem(row, 5, QTableWidgetItem(str(xml_total)))
        
        # STATUS (por enquanto sempre pending - builder vai atualizar)
        status_item = QTableWidgetItem("pending")
        self.color_status_cell(status_item, "pending")
        self.table.setItem(row, 6, status_item)
        
        # Info
        xml_class_id = entry.get('xml_class_id', 'N/A')
        info_text = f"ClassID: {xml_class_id}"
        self.table.setItem(row, 7, QTableWidgetItem(info_text))
    
    def color_status_cell(self, item, status):
        """Aplica cores baseadas no status"""
        if status == 'consistent':
            item.setBackground(QColor(0, 255, 0, 50))  # Verde claro
        elif status == 'inconsistent':
            item.setBackground(QColor(255, 0, 0, 50))  # Vermelho claro
        elif status == 'missing':
            item.setBackground(QColor(255, 255, 0, 50))  # Amarelo claro
        elif status == 'pending':
            item.setBackground(QColor(135, 206, 250, 50))  # Azul claro
        else:
            item.setBackground(QColor(200, 200, 200, 50))  # Cinza
    
    def get_filtered_entries(self):
        """Retorna entradas filtradas baseadas nas seleções"""
        status_filter = self.status_filter.currentText()
        site_filter = self.site_filter.currentText()
        
        filtered = self.audit_entries
        
        # Filtro por status
        if status_filter == "Consistentes":
            filtered = [e for e in filtered if e.get('status') == 'consistent']
        elif status_filter == "Inconsistentes":
            filtered = [e for e in filtered if e.get('status') == 'inconsistent']
        elif status_filter == "Faltando":
            filtered = [e for e in filtered if e.get('status') == 'missing']
        elif status_filter == "Extraíveis":
            filtered = [e for e in filtered if e.get('is_extractable', False)]
        elif status_filter == "Não Extraíveis":
            filtered = [e for e in filtered if not e.get('is_extractable', True)]
        
        # Filtro por site/tipo
        if site_filter == "SkillTree":
            filtered = [e for e in filtered if e.get('_audit_type') == 'skilltree']
        elif site_filter != "Todos":
            filtered = [e for e in filtered if 
                       e.get('_audit_type') == 'item' and 
                       e.get('site_type', '').upper() == site_filter.upper()]
        
        return filtered
    
    def apply_filters(self):
        """Aplica os filtros atuais"""
        self.update_table()
        self.update_stats()
    
    def update_stats(self):
        """Atualiza estatísticas na interface"""
        items = [e for e in self.audit_entries if e.get('_audit_type') == 'item']
        skilltrees = [e for e in self.audit_entries if e.get('_audit_type') == 'skilltree']
        
        total = len(self.audit_entries)
        consistent = len([e for e in items if e.get('status') == 'consistent'])
        inconsistent = len([e for e in items if e.get('status') == 'inconsistent'])
        missing = len([e for e in items if e.get('status') == 'missing'])
        extractable = len([e for e in items if e.get('is_extractable', False)])
        
        self.stats_label.setText(
            f"Items: {len(items)} | SkillTrees: {len(skilltrees)} | "
            f"Consistentes: {consistent} | "
            f"Inconsistentes: {inconsistent} | "
            f"Faltando: {missing}"
        )
    
    def on_selection_changed(self):
        """Quando uma linha é selecionada, mostra detalhes"""
        selected_items = self.table.selectedItems()
        if not selected_items:
            return
        
        row = selected_items[0].row()
        filtered_entries = self.get_filtered_entries()
        
        if row < len(filtered_entries):
            entry = filtered_entries[row]
            details = self.format_details(entry)
            self.details_text.setText(details)
    
    def format_details(self, entry):
        """Formata detalhes para exibição"""
        entry_type = entry.get('_audit_type', 'item')
        
        if entry_type == 'item':
            return f"""
=== DETALHES DA AUDITORIA - ITEM ===
Item ID: {entry['item_id']}
Site: {entry['site_type'].upper()}
Extraível: {'✅ Sim' if entry['is_extractable'] else '❌ Não'}

AÇÕES:
• DAT: {entry['dat_action']}
• SITE: {entry['site_action']} 
• EXPECTED: {entry['expected_action']}
• XML: {entry['xml_action'] or "NONE"}

STATUS: {entry['status'].upper()}
            """.strip()
        
        elif entry_type == 'skilltree':
            return f"""
=== DETALHES DA AUDITORIA - SKILLTREE ===
Class Slug: {entry.get('class_slug', 'N/A')}
XML Class: {entry.get('xml_class_name', 'N/A')}
Site: {entry.get('site_type', 'N/A').upper()}

SKILLS:
• Site Total: {entry.get('site_total_skills', 0)}
• XML Total: {entry.get('xml_total_skills', 0)}
• XML ClassID: {entry.get('xml_class_id', 'N/A')}

Timestamp: {entry.get('timestamp', 'N/A')}

Note: Use SkillTree Builder para comparação detalhada
            """.strip()
        
        return "Tipo de auditoria desconhecido"
    
    def export_audit(self):
        """Exporta auditoria completa para arquivo"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"auditoria_{timestamp}.txt"
            
            items = [e for e in self.audit_entries if e.get('_audit_type') == 'item']
            skilltrees = [e for e in self.audit_entries if e.get('_audit_type') == 'skilltree']
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("=== RELATÓRIO DE AUDITORIA COMPLETO ===\n\n")
                f.write(f"Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total de itens auditados: {len(items)}\n")
                f.write(f"Total de skilltrees auditados: {len(skilltrees)}\n\n")
                
                # Estatísticas de items
                if items:
                    consistent = len([e for e in items if e.get('status') == 'consistent'])
                    inconsistent = len([e for e in items if e.get('status') == 'inconsistent'])
                    missing = len([e for e in items if e.get('status') == 'missing'])
                    extractable = len([e for e in items if e.get('is_extractable', False)])
                    
                    f.write("=== ESTATÍSTICAS - ITEMS ===\n")
                    f.write(f"Consistentes: {consistent}\n")
                    f.write(f"Inconsistentes: {inconsistent}\n")
                    f.write(f"Faltando: {missing}\n")
                    f.write(f"Extraíveis: {extractable}\n\n")
                    
                    f.write("=== DETALHES POR ITEM ===\n\n")
                    
                    for i, entry in enumerate(items, 1):
                        f.write(f"{i}. Item: {entry['item_id']} | Site: {entry['site_type']}\n")
                        f.write(f"   DAT: {entry['dat_action']}\n")
                        f.write(f"   SITE: {entry['site_action']}\n")
                        f.write(f"   EXPECTED: {entry['expected_action']}\n")
                        f.write(f"   XML: {entry['xml_action'] or 'NONE'}\n")
                        f.write(f"   STATUS: {entry['status']}\n")
                        f.write(f"   EXTRAÍVEL: {'Sim' if entry['is_extractable'] else 'Não'}\n\n")
                
                # Estatísticas de skilltrees
                if skilltrees:
                    f.write("=== SKILLTREES AUDITADOS ===\n\n")
                    for i, entry in enumerate(skilltrees, 1):
                        f.write(f"{i}. Class: {entry.get('class_slug', 'N/A')} | ")
                        f.write(f"XML: {entry.get('xml_class_name', 'N/A')}\n")
                        f.write(f"   Site Skills: {entry.get('site_total_skills', 0)}\n")
                        f.write(f"   XML Skills: {entry.get('xml_total_skills', 0)}\n")
                        f.write(f"   ClassID: {entry.get('xml_class_id', 'N/A')}\n\n")
            
            QMessageBox.information(self, "Exportação Concluída", 
                                  f"Auditoria exportada para:\n{filename}")
            
        except Exception as e:
            QMessageBox.warning(self, "Erro na Exportação", 
                              f"Erro ao exportar auditoria: {str(e)}")
    
    def save_to_audit_file(self, audit_data):
        """Salva entrada individual em arquivo de log"""
        try:
            entry_type = audit_data.get('_audit_type', 'item')
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            with open("auditoria.txt", "a", encoding="utf-8") as f:
                if entry_type == 'item':
                    f.write(f"[{timestamp}] ITEM | {audit_data['item_id']} | ")
                    f.write(f"{audit_data['site_type']} | ")
                    f.write(f"DAT:{audit_data['dat_action']} | ")
                    f.write(f"SITE:{audit_data['site_action']} | ")
                    f.write(f"EXP:{audit_data['expected_action']} | ")
                    f.write(f"XML:{audit_data['xml_action'] or 'NONE'} | ")
                    f.write(f"STATUS:{audit_data['status']} | ")
                    f.write(f"EXT:{'YES' if audit_data['is_extractable'] else 'NO'}\n")
                elif entry_type == 'skilltree':
                    f.write(f"[{timestamp}] SKILLTREE | {audit_data.get('class_slug', 'N/A')} | ")
                    f.write(f"XML:{audit_data.get('xml_class_name', 'N/A')} | ")
                    f.write(f"SITE:{audit_data.get('site_total_skills', 0)} | ")
                    f.write(f"XML:{audit_data.get('xml_total_skills', 0)}\n")
        except:
            pass
    
    def clear_audit(self):
        """Limpa todos os dados de auditoria"""
        reply = QMessageBox.question(
            self, "Confirmar Limpeza",
            "Tem certeza que deseja limpar todos os dados de auditoria?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.audit_entries.clear()
            self.table.setRowCount(0)
            self.details_text.clear()
            self.update_stats()
            
            # Limpar arquivo de log
            try:
                Path("auditoria.txt").unlink(missing_ok=True)
            except:
                pass