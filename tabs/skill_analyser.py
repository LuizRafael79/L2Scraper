import json
import os
import re
import subprocess
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                           QPushButton, QLabel, QTextEdit,
                           QGroupBox, QGridLayout, QSplitter,
                           QComboBox, QLineEdit, QListWidget, QListWidgetItem,
                           QTabWidget, QScrollArea, QApplication, QCompleter)
from PyQt6.QtCore import Qt
from core.skill_name_parser import SkillNameParser

ROBUST_MAP = {
    r"power": ("PhysicalDamage", "power"),
    r"ignore.*?shield.*?defen[cs]e": ("PhysicalDamage", "ignoreShieldDefence"),
    r"ignores.*?defen[cs]e": ("PhysicalDamage", "pDefMod"),
    r"P\.?\s?Atk\.?": ("PhysicalAttack", "amount"),
    r"M\.?\s?Atk\.?": ("MagicalAttack", "amount"),
    r"PvE\s?damage": ("PvePhysicalAttackDamageBonus", "amount"),
    r"Sleep\s?Resist": ("DefenceTrait", "SLEEP"),
    r"Paralysis\s?Resist": ("DefenceTrait", "PARALYZE"),
    r"pvp: attacks up to (\d+) targets": ("PhysicalDamage", "pvpTargetCount"),
    r"pve: attacks up to (\d+) targets": ("PhysicalDamage", "pveTargetCount"),
}

class SkillParserTab(QWidget):
    """Effect Handlers Reference & Editor with Abnormal Preview"""
    
    def __init__(self, config=None, database=None):
            super().__init__()
            self.config = config
            self.database = database
            self.skill_name_parser = SkillNameParser("databases/skills_essence.dat")
            
            # Caminhos absolutos
            base_path = os.path.dirname(os.path.abspath(__file__))
            self.json_path = os.path.join(base_path, "effects_list.json")
            self.abnormal_json_path = os.path.join(base_path, "abnormal_list.json")
            
            # 1. Carrega os Handlers (Efeitos de Skill)
            self.effect_handlers = self.load_all_effect_handlers()
            
            # 2. Carrega os Abnormals (Visual)
            self.abnormal_db = self.load_abnormal_db()
            
            # 3. Gera o mapeamento Nome -> ID
            self.abnormal_name_map = self.generate_abnormal_map()
            
            self.setup_ui()

    def load_all_effect_handlers(self):
        """Carrega a biblioteca via JSON com verificação de caminho"""
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Erro ao carregar JSON em {self.json_path}: {e}")
        return {}

    def generate_abnormal_map(self):
        """Transforma a estrutura do seu JSON em um mapa de busca"""
        mapping = {}
        if not self.abnormal_db:
            print("⚠️ Aviso: Banco de dados de Abnormals está vazio!")
            return mapping

        for ave_id, effects in self.abnormal_db.items():
            for effect in effects:
                if 'name' in effect:
                    # 's_trans_deco' -> 'S_TRANS_DECO'
                    clean_name = effect['name'].upper()
                    mapping[clean_name] = ave_id
        
        print(f"✅ Mapa de nomes gerado: {len(mapping)} entradas.")
        return mapping

    def load_abnormal_db(self):
        """Carrega o mapeamento de IDs para arquivos UKX"""
        if os.path.exists(self.abnormal_json_path):
            try:
                with open(self.abnormal_json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f"✅ {len(data)} IDs de Abnormals carregados.")
                    return data
            except Exception as e:
                print(f"❌ Erro ao ler abnormal_list.json: {e}")
        else:
            print(f"❌ Arquivo não encontrado: {self.abnormal_json_path}")
        return {}

    def save_to_json(self):
        """Salva o estado atual no arquivo JSON"""
        try:
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(self.effect_handlers, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Erro ao salvar JSON: {e}")
            return False

    def setup_ui(self):
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        
        # Aba 1: Library
        self.browser_tab = self.create_browser_tab()
        self.tabs.addTab(self.browser_tab, "📚 Library")
        
        # Aba 2: Analyser
        self.analyser_tab = self.create_analyser_tab()
        self.tabs.addTab(self.analyser_tab, "🔍 Analyser")

        # Aba 3: Editor
        self.editor_tab = self.create_editor_tab()
        self.tabs.addTab(self.editor_tab, "🛠️ Editor")
        
        # Aba 4: Abnormal Browser
        self.abnormal_tab = self.create_abnormal_browser_tab()
        self.tabs.addTab(self.abnormal_tab, "🌌 Abnormals")
        
        layout.addWidget(self.tabs)

    def create_browser_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        header = QGroupBox("Explorador")
        h_layout = QHBoxLayout(header)
        self.total_label = QLabel(f"Handlers: <b>{len(self.effect_handlers)}</b>")
        h_layout.addWidget(self.total_label)
        layout.addWidget(header)

        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar por nome...")
        self.search_input.textChanged.connect(self.filter_effects)
        
        self.category_filter = QComboBox()
        self.update_category_list()
        self.category_filter.currentTextChanged.connect(self.filter_effects)
        
        search_layout.addWidget(QLabel("🔍"))
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(QLabel("📁"))
        search_layout.addWidget(self.category_filter)
        layout.addLayout(search_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.effects_list = QListWidget()
        self.effects_list.currentItemChanged.connect(self.show_effect_details)
        
        details_widget = QWidget()
        d_layout = QVBoxLayout(details_widget)
        self.effect_name_label = QLabel("<b>Selecione um efeito</b>")
        self.effect_name_label.setStyleSheet("font-size: 16px; color: #4ec9b0;")
        self.effect_description_label = QLabel("")
        self.effect_description_label.setWordWrap(True)
        self.params_display = QTextEdit()
        self.params_display.setReadOnly(True)
        self.example_display = QTextEdit()
        self.example_display.setReadOnly(True)
        
        btn_layout = QHBoxLayout()
        copy_btn = QPushButton("📋 Copiar XML")
        copy_btn.clicked.connect(self.copy_example)
        edit_mode_btn = QPushButton("🛠️ EDITAR ESTE EFEITO")
        edit_mode_btn.setStyleSheet("background-color: #3e4f3a;")
        edit_mode_btn.clicked.connect(self.send_to_editor)
        
        btn_layout.addWidget(copy_btn)
        btn_layout.addWidget(edit_mode_btn)

        d_layout.addWidget(self.effect_name_label)
        d_layout.addWidget(self.effect_description_label)
        d_layout.addWidget(QLabel("<b>Parâmetros:</b>"))
        d_layout.addWidget(self.params_display)
        d_layout.addWidget(QLabel("<b>Exemplo:</b>"))
        d_layout.addWidget(self.example_display)
        d_layout.addLayout(btn_layout)

        splitter.addWidget(self.effects_list)
        splitter.addWidget(details_widget)
        layout.addWidget(splitter)
        
        self.filter_effects()
        return widget

    def create_analyser_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        header = QGroupBox("Analisador de Descrições")
        layout.addWidget(header)
        
        self.description_input = QTextEdit()
        self.description_input.setPlaceholderText("Ex: Max HP +20%. Stun for 5 sec...")
        self.description_input.setStyleSheet("background-color: #2d2d2d; color: #dcdcdc;")
        layout.addWidget(self.description_input)
        
        search_layout = QHBoxLayout()
        self.skill_id_entry = QLineEdit()
        self.skill_id_entry.setPlaceholderText("Digite o Skill ID (ex: 48934)")
        btn_fetch = QPushButton("📡 Buscar no DAT")
        btn_fetch.clicked.connect(lambda: self.load_skill_from_dat(self.skill_id_entry.text()))

        search_layout.addWidget(self.skill_id_entry)
        search_layout.addWidget(btn_fetch)
        layout.insertLayout(1, search_layout) # Insere no topo da aba

        self.analysis_output = QTextEdit()
        self.analysis_output.setReadOnly(True)
        self.analysis_output.setStyleSheet("background-color: #1e1e1e; color: #4ec9b0;")
        layout.addWidget(QLabel("Efeitos Detectados:"))
        layout.addWidget(self.analysis_output)
        return widget

    def create_editor_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        form_group = QGroupBox("Editor de Handlers")
        form = QGridLayout(form_group)
        
        self.edit_name = QLineEdit(); self.edit_name.setReadOnly(True)
        self.edit_cat = QLineEdit()
        self.edit_desc = QTextEdit()
        self.edit_params = QTextEdit()
        self.edit_example = QTextEdit()
        self.edit_example.setStyleSheet("font-family: 'Consolas'; color: #4ec9b0; background: #1e1e1e;")

        # DROPDOWN COM SEARCH PARA ABNORMALS
        self.abnormal_combo = QComboBox()
        self.abnormal_combo.setEditable(True)
        names = sorted(self.abnormal_name_map.keys())
        self.abnormal_combo.addItems(names)
        
        completer = QCompleter(names)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.abnormal_combo.setCompleter(completer)
        
        self.edit_abnormal_id = QLineEdit()
        self.edit_abnormal_id.setPlaceholderText("ID")
        self.edit_abnormal_id.setFixedWidth(60)
        
        self.abnormal_combo.currentTextChanged.connect(self.sync_abnormal_id)

        self.btn_preview_ave = QPushButton("👁️ Umodel")
        self.btn_preview_ave.clicked.connect(self.launch_umodel)
        
        ave_layout = QHBoxLayout()
        ave_layout.addWidget(self.abnormal_combo, stretch=1)
        ave_layout.addWidget(self.edit_abnormal_id)
        ave_layout.addWidget(self.btn_preview_ave)

        form.addWidget(QLabel("Nome (ID):"), 0, 0)
        form.addWidget(self.edit_name, 0, 1)
        form.addWidget(QLabel("Categoria:"), 1, 0)
        form.addWidget(self.edit_cat, 1, 1)
        form.addWidget(QLabel("Descrição:"), 2, 0)
        form.addWidget(self.edit_desc, 2, 1)
        form.addWidget(QLabel("Parâmetros:"), 3, 0)
        form.addWidget(self.edit_params, 3, 1)
        form.addWidget(QLabel("Abnormal Visual:"), 4, 0)
        form.addLayout(ave_layout, 4, 1)
        form.addWidget(QLabel("Exemplo XML:"), 5, 0)
        form.addWidget(self.edit_example, 5, 1)
        
        layout.addWidget(form_group)
        save_btn = QPushButton("💾 SALVAR ALTERAÇÕES NO JSON")
        save_btn.setStyleSheet("height: 40px; font-weight: bold; background-color: #2d5a27; color: white;")
        save_btn.clicked.connect(self.save_edited_effect)
        layout.addWidget(save_btn)
        return widget

    def create_abnormal_browser_tab(self):
        """Aba independente para buscar efeitos visuais"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        search_layout = QHBoxLayout()
        self.ab_search_input = QLineEdit()
        self.ab_search_input.setPlaceholderText("Filtrar Abnormals por ID ou Nome...")
        self.ab_search_input.textChanged.connect(self.filter_abnormals_list)
        search_layout.addWidget(QLabel("🔍"))
        search_layout.addWidget(self.ab_search_input)
        layout.addLayout(search_layout)

        self.ab_list_widget = QListWidget()
        self.ab_list_widget.currentRowChanged.connect(self.on_abnormal_list_selection)
        
        self.ab_detail_label = QLabel("Selecione um efeito")
        self.ab_detail_label.setStyleSheet("color: #4ec9b0; font-family: 'Consolas';")
        
        btn_preview = QPushButton("👁️ ABRIR NO UMODEL")
        btn_preview.clicked.connect(self.launch_umodel_from_list)
        
        layout.addWidget(self.ab_list_widget)
        layout.addWidget(self.ab_detail_label)
        layout.addWidget(btn_preview)
        
        self.filter_abnormals_list()
        return widget

    def sync_abnormal_id(self, name):
        if name in self.abnormal_name_map:
            self.edit_abnormal_id.setText(self.abnormal_name_map[name])

    def launch_umodel(self):
        ave_id = self.edit_abnormal_id.text().strip()
        self._execute_umodel(ave_id)

    def launch_umodel_from_list(self):
        current = self.ab_list_widget.currentItem()
        if current:
            ave_id = current.data(Qt.ItemDataRole.UserRole)
            self._execute_umodel(ave_id)

    def _execute_umodel(self, ave_id):
        if not ave_id or ave_id not in self.abnormal_db:
            print(f"ID {ave_id} não encontrado no banco.")
            return

        # Pega o primeiro efeito vinculado ao ID
        effect_data = self.abnormal_db[ave_id][0]
        
        # Caminhos - Certifique-se que o executável tem permissão (+x)
        umodel_path = "/home/luiz/git/Umodel/umodel" 
        l2_path = "/home/luiz/Lineage_Clients/SamuraiCrow" 
        
        # Dados do JSON
        package = effect_data['package'].strip()
        obj = effect_data['name'].strip()

        # Sintaxe oficial: umodel -path=... -view <package> <object>
        # Removendo extensões se houver, o umodel aceita só o nome do pacote
        clean_package = package.replace('.ukx', '').replace('.utx', '')

        cmd = [
            umodel_path,
            f"-path={l2_path}",
            "-view",
            clean_package,
            obj
        ]
        
        print(f"🚀 Disparando Umodel: {' '.join(cmd)}")
        
        try:
            # No Linux, rodar o processo de forma independente
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"❌ Erro ao abrir visualizador: {e}")

    def filter_effects(self):
        search = self.search_input.text().lower()
        cat = self.category_filter.currentText()
        self.effects_list.clear()
        for name, data in sorted(self.effect_handlers.items()):
            if cat != "Todas" and data["category"] != cat: continue
            if search and search not in name.lower(): continue
            item = QListWidgetItem(f"{name} ({data['category']})")
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.effects_list.addItem(item)

    def filter_abnormals_list(self):
        query = self.ab_search_input.text().lower()
        self.ab_list_widget.clear()
        for ave_id, effects in self.abnormal_db.items():
            name = effects[0]['name']
            if query in ave_id or query in name.lower():
                item = QListWidgetItem(f"ID: {ave_id} - {name.upper()}")
                item.setData(Qt.ItemDataRole.UserRole, ave_id)
                self.ab_list_widget.addItem(item)

    def on_abnormal_list_selection(self):
        current = self.ab_list_widget.currentItem()
        if not current: return
        ave_id = current.data(Qt.ItemDataRole.UserRole)
        data = self.abnormal_db[ave_id][0]
        self.ab_detail_label.setText(f"Package: {data['package']} | Object: {data['name']}")

    def show_effect_details(self, current, previous):
        if not current: return
        name = current.data(Qt.ItemDataRole.UserRole)
        data = self.effect_handlers[name]
        self.effect_name_label.setText(f"<b>{name}</b>")
        self.effect_description_label.setText(f"📝 {data['description']}")
        params_text = "".join([f"• <b>{p}</b>: {d}\n" for p, d in data["params"].items()])
        self.params_display.setHtml(params_text if params_text else "<i>Nenhum parâmetro</i>")
        self.example_display.setText(data["example"])

    def send_to_editor(self):
        current = self.effects_list.currentItem()
        if not current: return
        name = current.data(Qt.ItemDataRole.UserRole)
        data = self.effect_handlers[name]
        self.edit_name.setText(name)
        self.edit_cat.setText(data['category'])
        self.edit_desc.setPlainText(data['description'])
        params_str = "\n".join([f"{k}: {v}" for k, v in data['params'].items()])
        self.edit_params.setPlainText(params_str)
        self.edit_example.setPlainText(data['example'])
        self.tabs.setCurrentIndex(2)

    def save_edited_effect(self):
        name = self.edit_name.text()
        if not name: return
        new_params = {l.split(':')[0].strip(): l.split(':')[1].strip() 
                     for l in self.edit_params.toPlainText().split('\n') if ':' in l}
        self.effect_handlers[name] = {
            "category": self.edit_cat.text(), "description": self.edit_desc.toPlainText(),
            "params": new_params, "example": self.edit_example.toPlainText()
        }
        if self.save_to_json():
            self.update_category_list(); self.filter_effects(); self.tabs.setCurrentIndex(0)

    def update_category_list(self):
        current_cat = self.category_filter.currentText()
        self.category_filter.clear()
        cats = ["Todas"] + sorted(list(set(e["category"] for e in self.effect_handlers.values())))
        self.category_filter.addItems(cats)
        if current_cat in cats: self.category_filter.setCurrentText(current_cat)

    def copy_example(self):
        QApplication.clipboard().setText(self.example_display.toPlainText())

    def get_clean_essence_description(self, skill_data_tuple):
        """
        Pega a tupla vinda do id_map/skill_map e reconstrói a string final.
        Índice [4] = desc
        Índice [5] = desc_param
        """
        raw_desc = skill_data_tuple[4]
        raw_params = skill_data_tuple[5]
        
        if not raw_desc:
            return ""

        # Transforma a string "+30;+40;+0.3%" em uma lista
        params_list = raw_params.split(';')
        
        clean_desc = raw_desc
        # Substitui cada placeholder $s1, $s2... pelo valor correspondente
        for i, value in enumerate(params_list):
            placeholder = f"$s{i+1}"
            clean_desc = clean_desc.replace(placeholder, value)
        
        # Limpa as quebras de linha literais do DAT
        return clean_desc.replace('\\n', '\n')

    def load_skill_from_dat(self, skill_id):
        """
        Processes skill data by combining dynamic anchor mapping and 
        robust pattern matching via ROBUST_MAP.
        """
        matches = self.skill_name_parser.id_map.get(str(skill_id), [])
        if not matches:
            self.analysis_output.setHtml("<b style='color:red;'>❌ Skill ID not found.</b>")
            return

        sorted_matches = sorted(matches, key=lambda x: (int(x[2]), int(x[3])))
        
        # 1. Obter template base (Lv1)
        base_desc = ""
        for m in sorted_matches:
            if m[4].strip():
                base_desc = m[4]
                break
        
        # LOG DE DADOS BRUTOS (description_input)
        debug_log = f"<div style='color:#569cd6;'><b>Mapping Skill: {skill_id}</b></div>"
        debug_log += f"<div style='color:#ce9178;'>Template: {base_desc}</div><br>"

        anchor_map = {}
        
        # Identificação de placeholders no texto base
        if base_desc:
            clean_base = re.sub(r'<[^>]+>', '', base_desc).lower()
            found_anchors = re.findall(r'(\w+)\s*\$s(\d+)', clean_base, re.IGNORECASE)
            for word, idx_str in found_anchors:
                idx = int(idx_str) - 1
                word_low = word.lower()
                
                # Mapeamento de âncoras comuns
                if "power" in word_low:
                    anchor_map[idx] = ("PhysicalDamage", "power")
                elif any(x in word_low for x in ["ignores", "defen", "defence"]):
                    anchor_map[idx] = ("PhysicalDamage", "pDefMod")
                elif "atk" in word_low:
                    anchor_map[idx] = ("PhysicalAttack" if "p." in word_low else "MagicalAttack", "amount")
                
                if idx in anchor_map:
                    debug_log += f"🔗 Anchor: $s{idx_str} ({word}) -> {anchor_map[idx][1]}<br>"

        self.description_input.setHtml(debug_log)

        # 2. Processamento dos níveis consolidando placeholders e ROBUST_MAP
        consolidated = {}
        for data in sorted_matches:
            lvl_num = int(data[2])
            params_list = data[5].split(';')
            
            # Reconstrói o texto com placeholders marcados para as Regex
            temp_text = base_desc
            for i, p in enumerate(params_list):
                temp_text = temp_text.replace(f'$s{i+1}', f'[VAL{i}]')
            
            lines = temp_text.split('\n')
            for line in lines:
                line_clean = re.sub(r'<[^>]+>', '', line).strip().lower()
                if not line_clean: continue

                # Varre o ROBUST_MAP para cada linha
                for pattern, info in ROBUST_MAP.items():
                    handler, param = info[0], info[1]
                    match = re.search(pattern, line_clean, re.IGNORECASE)
                    
                    if match:
                        if handler not in consolidated: consolidated[handler] = {}
                        if param not in consolidated[handler]: consolidated[handler][param] = {}

                        val = "0"
                        # Prioridade 1: Valor vem de um placeholder
                        if "[val" in line_clean:
                            idx_match = re.search(r'\[val(\d+)\]', line_clean)
                            if idx_match:
                                idx = int(idx_match.group(1))
                                if idx < len(params_list):
                                    raw_val = re.sub(r'[^0-9.]', '', params_list[idx])
                                    if param == "pDefMod":
                                        try: val = str(round(1 - (float(raw_val) / 100), 2))
                                        except: val = "1.0"
                                    else:
                                        val = raw_val
                        else:
                            # Prioridade 2: Valor estático capturado pelo Grupo 1 da Regex
                            # Ex: "attacks up to (4) targets" -> captura o 4
                            try:
                                val = match.group(1) if match.groups() else "true"
                            except:
                                val = "true"

                        consolidated[handler][param][lvl_num] = val

        # 3. Construção do XML com a ordem de tags correta
        tag_priority = ['power', 'amount', 'pDefMod', 'pvpTargetCount', 'pveTargetCount', 'ignoreShieldDefence']

        final_xml = "\t\t<effects>\n"
        for handler, params in consolidated.items():
            final_xml += f'\t\t\t<effect name="{handler}">\n'
            sorted_params = sorted(params.keys(), key=lambda x: tag_priority.index(x) if x in tag_priority else 999)
            
            for p_name in sorted_params:
                levels = params[p_name]
                unique_vals = set(levels.values())
                if len(unique_vals) == 1:
                    final_xml += f'\t\t\t\t<{p_name}>{list(unique_vals)[0]}</{p_name}>\n'
                else:
                    final_xml += f'\t\t\t\t<{p_name}>\n'
                    for l in sorted(levels.keys()):
                        final_xml += f'\t\t\t\t\t<value level="{l}">{levels[l]}</value>\n'
                    final_xml += f'\t\t\t\t</{p_name}>\n'
            final_xml += '\t\t\t</effect>\n'
        final_xml += '\t\t</effects>'

        xml_view = f"<pre style='background:#1e1e1e; color:#d4d4d4; padding:10px;'>{final_xml.replace('<', '&lt;').replace('>', '&gt;')}</pre>"
        self.analysis_output.setHtml(xml_view)

    def inject_params(self, template, params_str):
        """Simple replacement of $s placeholders for basic display if needed."""
        if not template or not params_str: return template
        params = params_str.split(';')
        for i, p in enumerate(params):
            template = template.replace(f'$s{i+1}', p)
        return template