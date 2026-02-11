import json
import os
import re
from pathlib import Path
from lxml import etree
from PyQt6.QtWidgets import (QLabel, QSplitter, QListWidget, QPushButton, QWidget,
                            QVBoxLayout, QHBoxLayout, QDialog, QMessageBox, QTextEdit,
                            QListWidgetItem)
from PyQt6.QtCore import Qt
from core.handlers.scraper_handler import ScraperHandler
from core.handlers.xml_handler import XMLHandler
from core.handlers.skill_handler import SkillHandler
from core.database import DatabaseManager

# Se você quiser gerar o JSON na hora se ele não existir:
from core.tools.multilevel_generator import MultilevelGrouper 

class MultilevelSkillDialog(QDialog):
    """Modal para gerenciar skills multilevel usando o JSON pré-processado"""
    
    def __init__(self, parent, site_type):
        # Note: removi skill_problems do init, pois vamos ler do JSON mestre
        super().__init__(parent)
        self.parent_tab = parent
        self.site_type = site_type
        self.current_skill_data = None
        
        # Handlers
        self.scraper_handler = ScraperHandler()
        self.xml_handler = XMLHandler(site_type=site_type)
        self.database = DatabaseManager(self.parent_tab.config)
        self.skill_handler = SkillHandler(self.xml_handler, self.scraper_handler, self.database)
        
        self.setWindowTitle(f"Multilevel Skills Manager - {site_type.upper()}")
        self.resize(1200, 800)
        
        self.setup_ui()
        self.load_data() # <--- Carrega do JSON
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Header
        header_layout = QHBoxLayout()
        header_lbl = QLabel("<h2>Multilevel Skills Manager</h2>")
        header_layout.addWidget(header_lbl)
        
        # Botão para regerar o JSON (caso você tenha mudado algo no scraper)
        refresh_btn = QPushButton("🔄 Refresh Data (Re-run Grouper)")
        refresh_btn.clicked.connect(self.refresh_data)
        header_layout.addWidget(refresh_btn)
        
        layout.addLayout(header_layout)
        
        info = QLabel("Gera XMLs complexos baseados no agrupamento de itens por Skill ID.")
        layout.addWidget(info)
        
        # Splitter principal
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # --- ESQUERDA: Lista ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        left_layout.addWidget(QLabel("<b>Detected Multilevel Skills:</b>"))
        self.skills_list = QListWidget()
        self.skills_list.itemClicked.connect(self.on_skill_selected)
        left_layout.addWidget(self.skills_list)
        
        # Botão Batch
        self.fix_all_btn = QPushButton("🚀 Generate ALL XMLs")
        self.fix_all_btn.clicked.connect(self.auto_fix_all_skills)
        left_layout.addWidget(self.fix_all_btn)
        
        # --- DIREITA: Preview ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Info Box
        right_layout.addWidget(QLabel("<b>Skill Details:</b>"))
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(150)
        right_layout.addWidget(self.info_text)
        
        # XML Preview
        right_layout.addWidget(QLabel("<b>XML Output Preview:</b>"))
        self.xml_editor = QTextEdit()
        self.xml_editor.setReadOnly(True)
        self.xml_editor.setStyleSheet("font-family: Consolas; font-size: 12px;") # Monospace font
        right_layout.addWidget(self.xml_editor)
        
        # Botão Save Single
        self.save_btn = QPushButton("💾 Save This Skill XML")
        self.save_btn.clicked.connect(self.save_current_skill)
        self.save_btn.setEnabled(False)
        right_layout.addWidget(self.save_btn)
        
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        layout.addWidget(splitter)

    def load_data(self):
        """Carrega o JSON gerado pelo Grouper"""
        json_filename = f"multilevel_skills_{self.site_type}.json"
        
        if not os.path.exists(json_filename):
            QMessageBox.information(self, "Info", f"{json_filename} not found.\nRunning grouper for the first time...")
            self.refresh_data()
            return

        try:
            with open(json_filename, 'r', encoding='utf-8') as f:
                self.multilevel_data = json.load(f)
            
            self.populate_list()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load JSON: {e}")

    def refresh_data(self):
        """Roda a lógica do Grouper dentro da UI"""
        try:
            # Chama a classe que criamos no passo anterior
            items_dir = f"html_items_{self.site_type}"
            grouper = MultilevelGrouper(items_dir, self.site_type)
            grouper.run() # Isso gera o JSON no disco
            
            self.load_data() # Recarrega a UI
            QMessageBox.information(self, "Success", "Data refreshed from Scraper & Database!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Grouper failed: {e}")

    def populate_list(self):
        self.skills_list.clear()
        
        # Ordena por ID da Skill
        sorted_ids = sorted(self.multilevel_data.keys(), key=lambda x: int(x))
        
        for skill_id in sorted_ids:
            data = self.multilevel_data[skill_id]
            skill_name = data.get('skill_name', 'Unknown')
            levels = data.get('levels', [])
            max_lvl = data.get('max_level', '?')
            
            display_text = f"[{skill_id}] {skill_name} (Max Lv: {max_lvl})"
            
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, skill_id) # Guarda só o ID
            self.skills_list.addItem(item)
            
        self.fix_all_btn.setEnabled(True)

    def on_skill_selected(self, item):
        skill_id = item.data(Qt.ItemDataRole.UserRole)
        self.current_skill_data = self.multilevel_data.get(skill_id)
        
        if not self.current_skill_data:
            return

        # 1. Mostra Info Detalhada
        levels = self.current_skill_data.get('levels', [])
        info_str = f"Skill: {self.current_skill_data.get('skill_name')}\n"
        info_str += f"ID: {skill_id}\n"
        info_str += f"Levels defined: {len(levels)}\n\n"
        
        for lvl in levels:
            i_name = lvl.get('item_name')
            box = lvl.get('box_data', {})
            guaranteed = len(box.get('guaranteed_items', []))
            random = len(box.get('random_items', []))
            info_str += f"Lv {lvl['level']}: Item {lvl['item_id']} ({i_name})\n"
            info_str += f"   Box: {guaranteed} Guaranteed, {random} Random\n"
            
        self.info_text.setText(info_str)

        # 2. Gera XML Preview (Usando o método NOVO do SkillHandler)
        xml_preview = self.skill_handler.generate_multilevel_xml_from_json(skill_id, self.current_skill_data, self.site_type)
        
        if xml_preview:
            self.xml_editor.setText(xml_preview)
            self.save_btn.setEnabled(True)
        else:
            self.xml_editor.setText("")
            self.save_btn.setEnabled(False)

    def save_current_skill(self):
        if not self.current_skill_data: return
        
        skill_id = str(self.skills_list.currentItem().data(Qt.ItemDataRole.UserRole))
        xml_content = self.xml_editor.toPlainText()
        
        # Salva usando o XMLHandler (que tem o regex fix)
        success = self.xml_handler.save_skill_xml_internal(
            skill_id, xml_content, self.site_type, skip_confirmation=False
        )
        
        if success:
            # Opcional: Atualizar cor do item na lista para verde indicando salvo
            self.update_associated_items(skill_id, self.current_skill_data)
            
            # Feedback Visual
            self.skills_list.currentItem().setBackground(Qt.GlobalColor.green)
            QMessageBox.information(self, "Success", f"Skill {skill_id} and its items updated successfully!")

    def update_associated_items(self, skill_id, skill_data):
        """
        Itera sobre os levels da skill, abre os arquivos XML dos itens
        e aplica a transformação In-Place (Capsuled -> Skill).
        """
        levels = skill_data.get('levels', [])
        
        # Agrupar itens por arquivo para abrir/salvar apenas uma vez por arquivo
        items_by_file = {}
        
        # Diretório base
        if self.site_type == "essence":
            output_dir = Path("output_items_essence")
            base_items_dir = Path("items_essence")
        else:
            output_dir = Path("output_items_main")
            base_items_dir = Path("items_main")
            
        output_dir.mkdir(exist_ok=True)

        # 1. Mapear onde está cada item
        for lvl_data in levels:
            item_id = str(lvl_data['item_id'])
            
            # Cálculo do nome do arquivo (ex: 47300-47399.xml)
            try:
                block_num = int(item_id) // 100
                block_start = block_num * 100
                block_end = block_start + 99
                filename = f"{block_start:05d}-{block_end:05d}.xml"
                
                # Prioridade: Output > Original
                output_path = output_dir / filename
                original_path = base_items_dir / filename
                
                target_file = output_path if output_path.exists() else original_path
                
                if str(target_file) not in items_by_file:
                    items_by_file[str(target_file)] = {
                        'output_path': output_path, # Onde vamos salvar
                        'items_to_fix': []
                    }
                
                items_by_file[str(target_file)]['items_to_fix'].append({
                    'item_id': item_id,
                    'level': lvl_data['level']
                })
                
            except Exception as e:
                print(f"⚠️ Erro calculando arquivo para item {item_id}: {e}")

        # 2. Processar arquivo por arquivo (Performance + Segurança)
        success_count = 0
        
        for src_file, data in items_by_file.items():
            try:
                if not os.path.exists(src_file):
                    print(f"⚠️ Arquivo não encontrado: {src_file}")
                    continue

                # Carrega com LXML (Mesma config do ItemBuilder)
                parser = etree.XMLParser(remove_blank_text=False, remove_comments=False)
                tree = etree.parse(src_file, parser)
                root = tree.getroot()
                
                modified = False
                
                for item_info in data['items_to_fix']:
                    target_id = item_info['item_id']
                    target_level = item_info['level']
                    
                    # Busca o item no XML
                    items = root.xpath(f".//item[@id='{target_id}']")
                    if items:
                        item_elem = items[0]
                        # APLICA A TRANSFORMAÇÃO
                        self._transform_item_to_skill_inplace(item_elem, skill_id, target_level)
                        modified = True
                        success_count += 1
                    else:
                        print(f"⚠️ Item {target_id} não encontrado em {src_file}")

                if modified:
                    # Salva no diretório de output
                    out_path = data['output_path']
                    tree.write(str(out_path), encoding='utf-8', xml_declaration=True, pretty_print=False)
                    
                    # Fix Self-Closing Tags (Igual ao ItemBuilder)
                    with open(out_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    content = re.sub(r'(?<!\s)/>', ' />', content)
                    with open(out_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                        
                    print(f"💾 Itens salvos em: {out_path.name}")

            except Exception as e:
                print(f"❌ Erro processando arquivo {src_file}: {e}")

        print(f"✅ Total de itens atualizados: {success_count}")

    def _transform_item_to_skill_inplace(self, item_elem, skill_id, skill_level):
        """
        Replica a lógica 'SKILL MODE' do ItemBuilderTab.edit_item_inplace_lxml.
        Converte um item de caixa/extractable para um item de skill.
        """
        # 1. Atualizar default_action (SKILL_REDUCE é o padrão seguro para skills clickáveis)
        # Se quiser ser mais específico, poderia tentar adivinhar pelo tipo, mas SKILL_REDUCE funciona bem.
        self.skill_handler._update_or_add_set_tag_lxml(item_elem, 'default_action', 'SKILL_REDUCE')
        
        # 2. Atualizar handler para ItemSkills
        self.skill_handler._update_or_add_set_tag_lxml(item_elem, 'handler', 'ItemSkills')
        
        # 3. Remover tags de Extractable (capsuled_items, extractableCount)
        # Preservando o tail para não quebrar indentação
        capsuled_tail = '\n\t'
        for capsuled in item_elem.xpath('./capsuled_items'):
            if capsuled.tail:
                capsuled_tail = capsuled.tail
            item_elem.remove(capsuled)
        
        for tag in item_elem.xpath("./set[@name='extractableCountMin']"):
            item_elem.remove(tag)
        for tag in item_elem.xpath("./set[@name='extractableCountMax']"):
            item_elem.remove(tag)
            
        # 4. Adicionar/Atualizar a tag <skills>
        # Usa o método existente no SkillHandler que você já criou e validou
        self.skill_handler._update_or_create_skills_lxml(
            item_elem, 
            skill_id, 
            self.site_type, 
            capsuled_tail, # Passa o tail antigo para a nova tag ficar bonitinha
            override_level=skill_level # Importante: Passar o nível específico deste item!
        )

    def auto_fix_all_skills(self):
        reply = QMessageBox.question(
            self, 'Confirm Batch', 
            f"Are you sure you want to generate XMLs for all {self.skills_list.count()} skills?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            count = 0
            errors = 0
            
            for skill_id, data in self.multilevel_data.items():
                xml = self.skill_handler.generate_multilevel_xml_from_json(skill_id, data, self.site_type)
                if xml:
                    ok = self.xml_handler.save_skill_xml_internal(
                        skill_id, xml, self.site_type, skip_confirmation=True
                    )
                    if ok: count += 1
                    else: errors += 1
                else:
                    errors += 1
            
            QMessageBox.information(self, "Batch Complete", f"Generated: {count}\nErrors: {errors}")