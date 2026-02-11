from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QProgressBar, QTextEdit, QGroupBox, QGridLayout,
                             QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QFileDialog, QComboBox, QLineEdit, QMessageBox, QCheckBox)
from PyQt6.QtCore import pyqtSignal, Qt, QThread
from PyQt6.QtGui import QTextCursor, QFont, QSyntaxHighlighter, QTextCharFormat, QColor
import re
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
from collections import defaultdict
from difflib import SequenceMatcher


# ============================================================================
# XML SYNTAX HIGHLIGHTER
# ============================================================================
class XMLHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.tag_format = QTextCharFormat()
        self.tag_format.setForeground(QColor("#569CD6"))
        self.tag_format.setFontWeight(QFont.Weight.Bold)
        
        self.attr_name_format = QTextCharFormat()
        self.attr_name_format.setForeground(QColor("#9CDCFE"))
        
        self.attr_value_format = QTextCharFormat()
        self.attr_value_format.setForeground(QColor("#CE9178"))
        
        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor("#6A9955"))
        self.comment_format.setFontItalic(True)

    def highlightBlock(self, text):
        for match in re.finditer(r'</?[\w:]+', text):
            self.setFormat(match.start(), match.end() - match.start(), self.tag_format)
        
        for match in re.finditer(r'\b(\w+)=', text):
            self.setFormat(match.start(), match.end() - match.start() - 1, self.attr_name_format)
        
        for match in re.finditer(r'"[^"]*"', text):
            self.setFormat(match.start(), match.end() - match.start(), self.attr_value_format)
        
        for match in re.finditer(r'<!--.*?-->', text):
            self.setFormat(match.start(), match.end() - match.start(), self.comment_format)


# ============================================================================
# RELIC XML UPDATER CORE
# ============================================================================
class RelicXMLUpdater:
    
    GRADE_MAP = {
        1: 'COMMON', 2: 'ENHANCED', 3: 'SUPERIOR', 4: 'RARE',
        5: 'HEROIC', 6: 'LEGENDARY', 7: 'MYTHIC'
    }
    
    PATTERNS = {
        'COMMON': {
            1: {'summonChance': '660000000', 'compound': '0.65000', 'upgrade': '1.08333'},
            2: {'summonChance': '420000000', 'compound': '0.75000', 'upgrade': '1.25000'},
            3: {'summonChance': '70000000', 'compound': '0.95000', 'upgrade': '1.58333'},
            4: {'summonChance': '30000000', 'compound': '1.50000', 'upgrade': '2.50000'}
        },
        'ENHANCED': {
            1: {'summonChance': '396000000', 'compound': '0.35000', 'upgrade': '0.58333'},
            2: {'summonChance': '252000000', 'compound': '0.40000', 'upgrade': '0.66667'},
            3: {'summonChance': '43200000', 'compound': '0.45000', 'upgrade': '0.75000'},
            4: {'summonChance': '11250000', 'compound': '0.50000', 'upgrade': '0.83333'},
            5: {'summonChance': '3600000', 'compound': '0.55000', 'upgrade': '0.91667'}
        },
        'SUPERIOR': {
            1: {'summonChance': '33250000', 'compound': '0.07500', 'upgrade': '0.12500'},
            2: {'summonChance': '20125000', 'compound': '0.08000', 'upgrade': '0.13333'},
            3: {'summonChance': '3587500', 'compound': '0.08500', 'upgrade': '0.14167'},
            4: {'summonChance': '350000', 'compound': '0.09000', 'upgrade': '0.15000'}
        },
        'RARE': {
            1: {'summonChance': '5273400', 'compound': '0.00950', 'upgrade': '0.01583'},
            2: {'summonChance': '2726000', 'compound': '0.01000', 'upgrade': '0.01667'},
            3: {'summonChance': '517000', 'compound': '0.01500', 'upgrade': '0.02500'},
            4: {'summonChance': '47000', 'compound': '0.02000', 'upgrade': '0.03333'}
        },
        'HEROIC': {
            1: {'summonChance': '330000', 'compound': '0.00035', 'upgrade': '0.00058'},
            2: {'summonChance': '118500', 'compound': '0.00040', 'upgrade': '0.00067'},
            3: {'summonChance': '24000', 'compound': '0.00045', 'upgrade': '0.00075'}
        },
        'LEGENDARY': {
            1: {'summonChance': '1', 'compound': '3.30000', 'upgrade': '5.50000'}
        },
        'MYTHIC': {
            1: {'summonChance': '1', 'compound': '3.30000', 'upgrade': '5.50000'}
        }
    }
    
    def __init__(self):
        self.relics = []  # De DATs
        self.collections = []  # De DATs
        self.items_lookup = {}  # De items-essence.dat
        self.existing_relics = {}  # Do XML existente {id: element}
        self.existing_collections = {}  # Do XML existente {id: element}
        self.existing_coupons = {}  # Do XML existente {itemId: element}
    
    @staticmethod
    def infer_tier(relic_id):
        if relic_id <= 10:
            return 1
        elif relic_id <= 30:
            return 2
        elif relic_id <= 90:
            return 3
        elif relic_id <= 120:
            return 4
        return 2
    
    def load_existing_xmls(self, relic_xml_path, collection_xml_path, coupon_xml_path):
        """Carrega XMLs existentes para edição incremental"""
        try:
            # Carregar RelicData.xml existente
            tree = ET.parse(relic_xml_path)
            root = tree.getroot()
            
            # Mapear relics existentes
            self.existing_relics = {}
            for relic_elem in root.findall('relic'):
                relic_id = int(relic_elem.get('id'))
                self.existing_relics[relic_id] = relic_elem
            
            # Carregar RelicCollectionData.xml
            tree = ET.parse(collection_xml_path)
            root = tree.getroot()
            
            self.existing_collections = {}
            for col_elem in root.findall('relicCollection'):
                col_id = int(col_elem.get('id'))
                self.existing_collections[col_id] = col_elem
            
            # Carregar RelicCouponData.xml
            tree = ET.parse(coupon_xml_path)
            root = tree.getroot()
            
            self.existing_coupons = {}
            self.existing_simple_coupons = {}  # Apenas cupons simples
            self.existing_complex_coupons = []  # Cupons complexos
            
            for coupon_elem in root.findall('coupon'):
                item_id = coupon_elem.get('itemId')
                relic_id = coupon_elem.get('relicId')
                
                # Verificar se é cupom SIMPLES (tem relicId e NÃO tem elementos filhos)
                if relic_id and len(coupon_elem) == 0:
                    # Cupom simples: relicId + itemId, sem elementos filhos
                    self.existing_simple_coupons[relic_id] = {
                        'item_id': item_id,
                        'element': coupon_elem
                    }
                else:
                    # Cupom complexo (tem chanceGroups, disabledDolls, etc)
                    self.existing_complex_coupons.append(coupon_elem)
                
                if item_id:
                    self.existing_coupons[item_id] = coupon_elem
            
            print(f"DEBUG: {len(self.existing_simple_coupons)} cupons simples")
            print(f"DEBUG: {len(self.existing_complex_coupons)} cupons complexos")
            
            return True
            
        except Exception as e:
            print(f"Erro ao carregar XMLs existentes: {e}")
            return False
    
    def parse_relics_main(self, filepath):
        """Parse relic_main.dat - CORRIGIDO PARA MYTHIC"""
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        self.relics = []
        
        # CADA LINHA É UMA RELIC COMPLETA
        for line in content.split('\n'):
            line = line.strip()
            if not line or 'relics_main_begin' not in line:
                continue
            
            current_relic = {}
            
            # ID da relic
            match = re.search(r'relics_id=(\d+)', line)
            if match:
                current_relic['id'] = int(match.group(1))
            
            # ID do item (Doll)
            match = re.search(r'item_id=(\d+)', line)
            if match:
                current_relic['item_id'] = int(match.group(1))
            
            # Grade
            match = re.search(r'grade=(\d+)', line)
            if match:
                grade_num = int(match.group(1))
                current_relic['grade'] = self.GRADE_MAP.get(grade_num, 'COMMON')
            
            # Skills - CORREÇÃO AQUI PARA MYTHIC
            # Formato Mythic: {{50579;6;72};{50579;7;72};{50579;8;72};{50579;9;72}}
            # Formato normal: {{50578;1;1}}
            match = re.search(r'skill_id=\{\{([^}]+(?:\};[^}]+)*)\}\}', line)
            if match:
                skills_text = match.group(1)
                current_relic['skills'] = []
                
                # Split por };{ para pegar múltiplos skills
                skill_parts = skills_text.split('};{')
                
                for skill_part in skill_parts:
                    # Limpar chaves
                    skill_part = skill_part.replace('{', '').replace('}', '')
                    parts = skill_part.split(';')
                    if len(parts) >= 3:
                        current_relic['skills'].append({
                            'id': int(parts[0]),
                            'level': int(parts[1]),
                            'combatPower': int(parts[2])
                        })
            
            # Level
            match = re.search(r'level=(\d+)', line)
            if match:
                current_relic['level'] = int(match.group(1))
            
            # Adicionar se tiver dados mínimos
            if 'id' in current_relic and 'skills' in current_relic:
                self.relics.append(current_relic)
                
                # DEBUG
                if current_relic.get('grade') == 'MYTHIC':
                    print(f"DEBUG MYTHIC: ID={current_relic['id']}, Skills={len(current_relic['skills'])}")
        
        print(f"✅ Parseadas {len(self.relics)} relics")
        
        # Contar Mythics
        mythic_count = sum(1 for r in self.relics if r.get('grade') == 'MYTHIC')
        print(f"📊 Mythic relics: {mythic_count}")
        
        return self.relics
    
    def parse_collection(self, filepath):
        """Parse relic_collection.dat - CORRIGIDO"""
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        self.collections = []
        
        # CADA LINHA É UMA COLLECTION COMPLETA
        for line in content.split('\n'):
            line = line.strip()
            if not line or 'relics_collection_begin' not in line:
                continue
            
            current_collection = {}
            
            # ID da collection
            match = re.search(r'relics_collection_id=(\d+)', line)
            if match:
                current_collection['id'] = int(match.group(1))
            
            # Categoria
            match = re.search(r'category=(\d+)', line)
            if match:
                current_collection['category'] = int(match.group(1))
            
            # Nome da collection
            match = re.search(r'relics_collection_name=\[([^\]]+)\]', line)
            if match:
                current_collection['name'] = match.group(1)
            
            # Option ID
            match = re.search(r'option_id=(\d+)', line)
            if match:
                current_collection['optionId'] = int(match.group(1))
            
            # Relics necessárias - formato: {{1;0};{3;0};{5;0}}
            match = re.search(r'need_relics=\{\{([^}]+(?:\};[^}]+)*)\}\}', line)
            if match:
                relics_text = match.group(1)
                current_collection['relics'] = []
                
                # Split por };{ para pegar múltiplos pares
                relic_parts = relics_text.split('};{')
                
                for relic_part in relic_parts:
                    # Limpar chaves
                    relic_part = relic_part.replace('{', '').replace('}', '')
                    parts = relic_part.split(';')
                    if len(parts) >= 2:
                        current_collection['relics'].append({
                            'id': int(parts[0]),
                            'enchantLevel': int(parts[1])
                        })
            
            # Adicionar se tiver dados mínimos
            if 'id' in current_collection and 'relics' in current_collection:
                self.collections.append(current_collection)
        
        print(f"✅ Parseadas {len(self.collections)} collections")
        return self.collections
    
    def get_relic_name_for_comment(self, relic_id):
        """Obtém o nome da Doll para usar nos comentários"""
        # Primeiro, procurar nos relics já parseados
        for relic in self.relics:
            if relic['id'] == relic_id:
                item_id = relic.get('item_id')
                if item_id:
                    full_name = self.items_lookup.get(item_id, "")
                    if full_name:
                        # Extrair nome limpo
                        doll_name = self.extract_doll_name(full_name)
                        
                        # Adicionar grade
                        grade = relic.get('grade', 'COMMON')
                        grade_display = "Mythic" if grade == "MYTHIC" else grade.capitalize()
                        
                        return f"{grade_display} {doll_name} Doll"
        
        return f"Relic {relic_id}"
    
    def parse_items_essence(self, filepath):
        """Parse items-essence.dat - CORRIGIDO PARA FORMATO TABULAR"""
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        self.items_lookup = {}
        
        # CADA LINHA É UM ITEM COMPLETO
        for line in content.split('\n'):
            line = line.strip()
            if not line or 'item_name_begin' not in line:
                continue
            
            # Extrair id e name da mesma linha
            id_match = re.search(r'id=(\d+)', line)
            name_match = re.search(r'name=\[([^\]]+)\]', line)
            
            if id_match and name_match:
                item_id = int(id_match.group(1))
                item_name = name_match.group(1)
                self.items_lookup[item_id] = item_name
        
        return self.items_lookup
    
    def parse_etcitemgrp(self, filepath):
        """Parse etcitemgrp.dat para obter material_type dos itens"""
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        self.item_materials = {}  # item_id -> material_type
        
        for line in content.split('\n'):
            line = line.strip()
            if not line or 'item_begin' not in line:
                continue
            
            current_item = {}
            
            # Object ID (item ID)
            match = re.search(r'object_id=(\d+)', line)
            if match:
                item_id = int(match.group(1))
            
            # Material Type
            match = re.search(r'material_type=(\w+)', line)
            if match:
                material = match.group(1)
                self.item_materials[item_id] = material
        
        print(f"✅ Parseados {len(self.item_materials)} materiais de itens")
        
        # DEBUG: Verificar alguns coupons
        coupon_count = 0
        liquid_coupons = 0
        
        for item_id in self.item_materials:
            item_name = self.items_lookup.get(item_id, "")
            if 'coupon' in item_name.lower() and 'doll' in item_name.lower():
                coupon_count += 1
                if self.item_materials[item_id] == 'liquid':
                    liquid_coupons += 1
        
        print(f"DEBUG: {coupon_count} coupons Doll encontrados")
        print(f"DEBUG: {liquid_coupons} com material_type='liquid'")
        
        return self.item_materials
    
    def extract_doll_name(self, full_name):
        """Extrai nome da doll removendo sufixos - VERSÃO MELHORADA"""
        if not full_name:
            return ""
        
        name = full_name.strip()
        
        # Remove " Doll" no final (case insensitive)
        name = re.sub(r'\s+Doll\s*$', '', name, flags=re.IGNORECASE)
        
        # Remove conteúdo entre parênteses
        name = re.sub(r'\s*\([^)]*\)', '', name)
        
        # Remove prefixos de grade
        name = re.sub(r'^(Common|Enhanced|Superior|Rare|Heroic|Legendary|Mythic)\s+', 
                    '', name, flags=re.IGNORECASE)
        
        # Remove números no final (ex: "Anais 1" -> "Anais")
        name = re.sub(r'\s+\d+$', '', name)
        
        return name.strip()
    
    def get_base_relic_id(self, relic_id):
        """Encontra o ID base da família (menor ID com mesmo primeiro skill)"""
        # Encontrar a relic atual
        current_relic = next((r for r in self.relics if r['id'] == relic_id), None)
        if not current_relic or not current_relic.get('skills'):
            return relic_id
        
        # Pegar o primeiro skill ID
        first_skill_id = current_relic['skills'][0]['id']
        
        # Encontrar todas as relics com mesmo primeiro skill
        same_family = []
        for relic in self.relics:
            if relic.get('skills') and relic['skills'][0]['id'] == first_skill_id:
                same_family.append(relic)
        
        # Retornar o menor ID da família
        if same_family:
            return min(relic['id'] for relic in same_family)
        
        return relic_id
    
    def update_relic_data_xml(self, output_path):
        # Tenta método simples primeiro
        result = self.update_relic_data_xml_simple(output_path)
        if "Erro" in result:
            # Se falhar, usa fallback
            return self.update_relic_data_xml_fallback(output_path)
        return result

    def update_collection_xml(self, output_path):
        # Tenta método simples primeiro
        result = self.update_collection_xml_simple(output_path)
        if "Erro" in result:
            # Se falhar, usa fallback
            return self.update_collection_xml_fallback(output_path)
        return result
        
    def update_relic_data_xml_fallback(self, output_path):
        """
        FALLBACK: recria XML completo (só usar se o método simples falhar)
        """
        try:
            # Carregar XML existente para preservar estrutura
            tree = ET.parse(output_path)
            root = tree.getroot()
            
            # Mapear relics existentes
            existing_relics = {}
            for relic_elem in root.findall('relic'):
                relic_id = int(relic_elem.get('id'))
                existing_relics[relic_id] = relic_elem
            
            # Adicionar novas relics
            added_count = 0
            for relic_data in sorted(self.relics, key=lambda x: x['id']):
                relic_id = relic_data['id']
                
                if relic_id not in existing_relics:
                    # Criar nova relic
                    relic = ET.SubElement(root, 'relic')
                    relic.set('id', str(relic_id))
                    relic.set('grade', relic_data['grade'])
                    
                    tier = self.infer_tier(relic_id)
                    pattern = self.PATTERNS.get(relic_data['grade'], {}).get(tier) or \
                            self.PATTERNS[relic_data['grade']][1]
                    
                    relic.set('summonChance', pattern['summonChance'])
                    relic.set('baseRelicId', str(self.get_base_relic_id(relic_id)))
                    relic.set('compoundChanceModifier', pattern['compound'])
                    relic.set('compoundUpGradeChanceModifier', pattern['upgrade'])
                    
                    for skill in relic_data.get('skills', []):
                        stat = ET.SubElement(relic, 'relicStat')
                        stat.set('enchantLevel', '0')
                        stat.set('skillId', str(skill['id']))
                        stat.set('skillLevel', str(skill['level']))
                        stat.set('combatPower', str(skill['combatPower']))
                    
                    added_count += 1
            
            # Salvar com pretty print
            xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent='\t')
            
            # Preservar header original (<?xml version="1.0" encoding="UTF-8"?>)
            lines = xml_str.split('\n')
            if len(lines) > 1 and '<?xml' in lines[0]:
                # Já tem header, manter
                final_xml = xml_str
            else:
                # Adicionar header
                final_xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str
            
            Path(output_path).write_text(final_xml, encoding='utf-8')
            
            return f"Fallback: adicionadas {added_count} novas relics (XML recriado)"
            
        except Exception as e:
            return f"Erro no fallback: {str(e)}"


    def update_collection_xml_fallback(self, output_path):
        """
        FALLBACK: recria XML completo (só usar se o método simples falhar)
        """
        try:
            # Carregar XML existente
            tree = ET.parse(output_path)
            root = tree.getroot()
            
            # Mapear collections existentes
            existing_collections = {}
            for col_elem in root.findall('relicCollection'):
                col_id = int(col_elem.get('id'))
                existing_collections[col_id] = col_elem
            
            # Adicionar novas collections
            added_count = 0
            for col_data in sorted(self.collections, key=lambda x: x['id']):
                col_id = col_data['id']
                
                if col_id not in existing_collections:
                    # Criar nova collection
                    collection = ET.SubElement(root, 'relicCollection')
                    collection.set('id', str(col_id))
                    collection.set('optionId', str(col_data['optionId']))
                    collection.set('category', str(col_data['category']))
                    collection.set('completeCount', str(len(col_data['relics'])))
                    collection.set('combatPower', '0')
                    
                    for relic_ref in col_data['relics']:
                        relic = ET.SubElement(collection, 'relic')
                        relic.set('id', str(relic_ref['id']))
                        relic.set('enchantLevel', str(relic_ref['enchantLevel']))
                    
                    added_count += 1
            
            # Salvar
            xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent='\t')
            
            lines = xml_str.split('\n')
            if len(lines) > 1 and '<?xml' in lines[0]:
                final_xml = xml_str
            else:
                final_xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str
            
            Path(output_path).write_text(final_xml, encoding='utf-8')
            
            return f"Fallback: adicionadas {added_count} novas collections (XML recriado)"
            
        except Exception as e:
            return f"Erro no fallback: {str(e)}"
        
    def update_relic_data_xml_simple(self, output_path):
        """
        Atualização SIMPLES: só adiciona novas relics, nunca modifica existentes
        """
        try:
            # 1. Ler XML existente linha por linha
            with open(output_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 2. Encontrar quais relics já existem no XML
            existing_relic_ids = set()
            for line in lines:
                if '<relic id="' in line:
                    match = re.search(r'id="(\d+)"', line)
                    if match:
                        existing_relic_ids.add(int(match.group(1)))
            
            # 3. Encontrar novas relics (que estão nos DATs mas não no XML)
            new_relics = []
            for relic in self.relics:
                if relic['id'] not in existing_relic_ids:
                    new_relics.append(relic)
            
            if not new_relics:
                return "Nenhuma nova relic para adicionar"
            
            # 4. Encontrar onde inserir (antes do </list>)
            insert_position = -1
            for i, line in enumerate(lines):
                if line.strip() == '</list>':
                    insert_position = i
                    break
            
            if insert_position == -1:
                return "Erro: não encontrou </list> no XML"
            
            # 5. Preparar novas relics para inserção
            new_lines = []
            for relic in sorted(new_relics, key=lambda x: x['id']):
                tier = self.infer_tier(relic['id'])
                pattern = self.PATTERNS.get(relic['grade'], {}).get(tier) or \
                        self.PATTERNS[relic['grade']][1]
                
                base_id = self.get_base_relic_id(relic['id'])
                
                # Obter nome da Doll para comentário
                doll_name = ""
                if relic.get('item_id'):
                    doll_name = self.items_lookup.get(relic['item_id'], "")
                    if doll_name:
                        doll_name = self.extract_doll_name(doll_name)
                
                # Formatar EXATAMENTE como no XML original
                indent = '\t'
                
                # Adicionar linha em branco antes (exceto primeira)
                if new_lines:
                    new_lines.append('\n')
                
                # Linha do relic com comentário
                grade_name = relic['grade']  # Já é "MYTHIC"
                grade_display_name = "Mythic" if grade_name == "MYTHIC" else grade_name.capitalize()
                
                if doll_name:
                    new_lines.append(f'{indent}<relic id="{relic["id"]}" grade="{grade_name}" summonChance="{pattern["summonChance"]}" baseRelicId="{base_id}" compoundChanceModifier="{pattern["compound"]}" compoundUpGradeChanceModifier="{pattern["upgrade"]}"> <!-- {grade_display_name} {doll_name} Doll -->\n')
                else:
                    new_lines.append(f'{indent}<relic id="{relic["id"]}" grade="{grade_name}" summonChance="{pattern["summonChance"]}" baseRelicId="{base_id}" compoundChanceModifier="{pattern["compound"]}" compoundUpGradeChanceModifier="{pattern["upgrade"]}">\n')
                
                # **CORREÇÃO: Para MYTHIC, usar os 4 skills do array**
                skills = relic.get('skills', [])
                
                if relic['grade'] == 'MYTHIC':
                    # Mythic: usar os 4 skills que já vêm no array
                    # Os 4 skills já têm os níveis corretos: 6, 7, 8, 9
                    # E correspondem a enchantLevel 0, 1, 2, 3
                    for i, skill in enumerate(skills[:4]):  # Pega apenas os 4 primeiros
                        if i == 0:
                            comment = f'{doll_name} Doll Lv. {skill["level"]}'
                        else:
                            comment = f'+{i} {doll_name} Doll'
                        
                        new_lines.append(f'{indent}\t<relicStat enchantLevel="{i}" skillId="{skill["id"]}" skillLevel="{skill["level"]}" combatPower="{skill["combatPower"]}" /> <!-- {comment} -->\n')
                else:
                    # Grades normais: apenas um skill
                    if skills:
                        skill = skills[0]  # Primeiro e único skill
                        comment = f'{doll_name} Doll Lv. {skill["level"]}' if doll_name else f'Level {skill["level"]}'
                        new_lines.append(f'{indent}\t<relicStat enchantLevel="0" skillId="{skill["id"]}" skillLevel="{skill["level"]}" combatPower="{skill["combatPower"]}" /> <!-- {comment} -->\n')
                
                new_lines.append(f'{indent}</relic>\n')
            
            # 6. Inserir no local correto
            lines[insert_position:insert_position] = new_lines
            
            # 7. Salvar
            with open(output_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            return f"Adicionadas {len(new_relics)} novas relics ao XML"
            
        except Exception as e:
            return f"Erro: {str(e)}"

    def update_collection_xml_simple(self, output_path):
        """
        Atualização SIMPLES: só adiciona novas collections, nunca modifica existentes
        """
        try:
            # 1. Ler XML existente linha por linha
            with open(output_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 2. Encontrar quais collections já existem no XML
            existing_collection_ids = set()
            for line in lines:
                if '<relicCollection id="' in line:
                    match = re.search(r'id="(\d+)"', line)
                    if match:
                        existing_collection_ids.add(int(match.group(1)))
            
            # 3. Encontrar novas collections (que estão nos DATs mas não no XML)
            new_collections = []
            for collection in self.collections:
                if collection['id'] not in existing_collection_ids:
                    new_collections.append(collection)
            
            if not new_collections:
                return "Nenhuma nova collection para adicionar"
            
            # 4. Encontrar onde inserir (antes do </list>)
            insert_position = -1
            for i, line in enumerate(lines):
                if line.strip() == '</list>':
                    insert_position = i
                    break
            
            if insert_position == -1:
                return "Erro: não encontrou </list> no XML"
            
            # 5. Preparar novas collections para inserção
            new_lines = []
            for collection in sorted(new_collections, key=lambda x: x['id']):
                indent = '\t'
                

                
                # Linha da collection com comentário
                collection_name = collection.get('name', '')
                if collection_name:
                    new_lines.append(f'{indent}<relicCollection id="{collection["id"]}" optionId="{collection["optionId"]}" category="{collection["category"]}" completeCount="{len(collection["relics"])}" combatPower="0"> <!-- {collection_name} -->\n')
                else:
                    new_lines.append(f'{indent}<relicCollection id="{collection["id"]}" optionId="{collection["optionId"]}" category="{collection["category"]}" completeCount="{len(collection["relics"])}" combatPower="0">\n')
                
                # Relics com comentários
                for relic in collection.get('relics', []):
                    relic_id = relic['id']
                    relic_name = self.get_relic_name_for_comment(relic_id)
                    new_lines.append(f'{indent}\t<relic id="{relic_id}" enchantLevel="{relic["enchantLevel"]}" /> <!-- {relic_name} -->\n')
                
                new_lines.append(f'{indent}</relicCollection>\n')
            
            # 6. Inserir no local correto
            lines[insert_position:insert_position] = new_lines
            
            # 7. Salvar
            with open(output_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            return f"Adicionadas {len(new_collections)} novas collections ao XML"
            
        except Exception as e:
            return f"Erro: {str(e)}"

    def find_coupon_suggestions(self, max_suggestions=50):
        """Versão SIMPLES e FUNCIONAL"""
        suggestions = {}
        
        # Palavras-chave obrigatórias
        REQUIRED_KEYWORDS = ['doll', 'summon', 'coupon']
        
        # 1. Quais relics já têm cupons
        relics_with_coupon = set(self.existing_simple_coupons.keys())
        
        # 2. Procurar cupons
        for relic in self.relics:
            relic_id = str(relic['id'])
            
            # Pular se já tem cupom
            if relic_id in relics_with_coupon:
                continue
            
            item_id = relic.get('item_id')
            if not item_id:
                continue
            
            item_name = self.items_lookup.get(item_id)
            if not item_name:
                continue
            
            relic_grade = relic.get('grade', 'COMMON')
            doll_name = self.extract_doll_name(item_name)
            
            # Buscar cupons da MESMA grade
            same_grade_matches = []
            
            for coupon_item_id, coupon_name in self.items_lookup.items():
                coupon_lower = coupon_name.lower()
                
                # Filtros básicos
                if not all(kw in coupon_lower for kw in REQUIRED_KEYWORDS):
                    continue
                
                if doll_name.lower() not in coupon_lower:
                    continue
                
                if 'package:' in coupon_lower or 'sealed' in coupon_lower:
                    continue  # Ignorar packages/sealed
                
                # VERIFICAÇÃO DE GRADE (case-insensitive)
                relic_grade_lower = relic_grade.lower()  # "enhanced"
                if relic_grade_lower not in coupon_lower:
                    continue  # ❌ Grade diferente
                
                # Cupom válido!
                same_grade_matches.append((coupon_item_id, coupon_name, 1.0))
            
            # Se encontrou cupom da mesma grade
            if same_grade_matches:
                suggestions[relic_id] = {
                    'doll_name': doll_name,
                    'original_name': item_name,
                    'item_id': item_id,
                    'grade': relic_grade,
                    'matches': same_grade_matches[:max_suggestions]  # Limitar
                }
        
        print(f"\n✅ {len(suggestions)} relics com cupons da mesma grade encontrados")
        
        # DEBUG: Mostrar quais Enhanced foram encontrados
        enhanced_found = [(rid, data['doll_name']) for rid, data in suggestions.items() 
                        if data['grade'] == 'ENHANCED']
        
        if enhanced_found:
            print(f"  Enhanced encontrados: {len(enhanced_found)}")
            for rid, doll in enhanced_found:
                print(f"    - Relic {rid}: {doll}")
        
        return suggestions
    
    def find_coupon_matches(self):
        """Encontra coupons correspondentes para cada relic"""
        coupon_matches = {}
        
        for relic in self.relics:
            relic_id = relic['id']
            item_id = relic.get('item_id')
            
            if not item_id:
                continue
            
            # 1. Pegar nome da Doll
            doll_name = self.items_lookup.get(item_id)
            if not doll_name:
                continue
            
            # 2. Extrair nome limpo (sem "Doll", etc.)
            clean_name = self.extract_doll_name(doll_name)
            
            # 3. Buscar coupons no items_lookup
            matches = []
            for coupon_item_id, coupon_name in self.items_lookup.items():
                # Filtro: deve conter "summon" e "coupon" no nome
                coupon_lower = coupon_name.lower()
                if 'summon' not in coupon_lower or 'coupon' not in coupon_lower:
                    continue
                
                # Verificar se o nome da Doll está no nome do coupon
                if clean_name.lower() in coupon_lower:
                    matches.append((coupon_item_id, coupon_name))
            
            if matches:
                coupon_matches[relic_id] = {
                    'doll_name': clean_name,
                    'original_name': doll_name,
                    'item_id': item_id,
                    'matches': matches  # Lista de (item_id, item_name)
                }
        
        return coupon_matches
    
    def generate_coupon_xml(self, output_path, coupon_mapping):
        """Atualiza RelicCouponData.xml - APENAS cupons SIMPLES"""
        if not coupon_mapping:
            return "Nenhum mapeamento para adicionar"
        
        try:
            # 1. Ler o XML como TEXTO
            with open(output_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 2. Encontrar onde inserir (ANTES do primeiro cupom complexo OU antes do </list>)
            insert_position = -1
            found_simple_section_end = False
            
            for i, line in enumerate(lines):
                # Procurar pelo primeiro cupom complexo (que tem > no final da tag)
                if '<coupon itemId="' in line and '>' in line and not '/>' in line:
                    insert_position = i
                    found_simple_section_end = True
                    print(f"DEBUG: Encontrado cupom complexo na linha {i}")
                    break
            
            # Se não encontrou cupom complexo, inserir antes do </list>
            if not found_simple_section_end:
                for i, line in enumerate(lines):
                    if line.strip() == '</list>':
                        insert_position = i
                        break
            
            if insert_position == -1:
                return "Erro: não encontrou onde inserir"
            
            # 3. Coletar quais cupons/relics já existem
            existing_coupon_items = set()
            relics_with_coupon = set()
            
            for line in lines:
                if '<coupon itemId=' in line and '/>' in line:  # Apenas cupons simples
                    # Pegar itemId
                    match = re.search(r'itemId="(\d+)"', line)
                    if match:
                        existing_coupon_items.add(match.group(1))
                    
                    # Pegar relicId
                    relic_match = re.search(r'relicId="(\d+)"', line)
                    if relic_match:
                        relics_with_coupon.add(int(relic_match.group(1)))
            
            print(f"DEBUG: {len(existing_coupon_items)} cupons simples já existem")
            print(f"DEBUG: {len(relics_with_coupon)} relics já têm cupons")
            
            # 4. Preparar NOVOS cupons para inserção
            new_lines = []
            added_count = 0
            skipped_count = 0
            
            for relic_id, coupon_data in sorted(coupon_mapping.items()):
                coupon_id = str(coupon_data['coupon_id'])
                relic_id_int = int(relic_id)
                
                # Pular se o cupom ITEM já existe
                if coupon_id in existing_coupon_items:
                    print(f"DEBUG: Cupom item {coupon_id} já existe, pulando")
                    skipped_count += 1
                    continue
                
                # Pular se a RELIC já tem cupom
                if relic_id_int in relics_with_coupon:
                    print(f"DEBUG: Relic {relic_id} já tem cupom, pulando")
                    skipped_count += 1
                    continue
                
                # Obter nome do cupom para comentário
                coupon_name = self.items_lookup.get(int(coupon_id), f"Cupom {coupon_id}")
                
                # Formatar
                indent = '\t'
                
                if new_lines:
                    new_lines.append('\n')
                
                new_lines.append(f'{indent}<coupon itemId="{coupon_id}" relicId="{relic_id}" summonCount="1" /> <!-- {coupon_name} -->\n')
                added_count += 1
            
            print(f"DEBUG: {added_count} novos, {skipped_count} pulados")
            
            # 5. Inserir no local correto se houver algo novo
            if new_lines:
                lines[insert_position:insert_position] = new_lines
                
                # 6. Salvar
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                
                return f"Adicionados {added_count} novos cupons SIMPLES ao XML ({skipped_count} já existiam)"
            else:
                return "Nenhum cupom novo para adicionar (todos já existem)"
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"Erro: {str(e)}"

# ============================================================================
# WORKER THREAD
# ============================================================================
class XMLUpdaterWorker(QThread):
    progress = pyqtSignal(int, int, str)
    log = pyqtSignal(str)
    finished = pyqtSignal(dict)
    
    def __init__(self, databases_dir, xml_files_dir, version = str):
        super().__init__()
        self.databases_dir = Path(databases_dir)
        self.xml_files_dir = Path(xml_files_dir)
        self.version = version  # "Main" ou "Essence"

    def get_file_paths(self):
        """Retorna os caminhos dos arquivos baseado na versão"""

        if not hasattr(self, 'version'):
            self.version = "Main"  # Default se não estiver definido

        suffix = "_main" if self.version == "Main" else "_essence"
        xml_folder = "relics_main" if self.version == "Main" else "relics_essence"
        
        return {
            'relic_main': self.databases_dir / f"relic_main{suffix}.dat",
            'relic_collection': self.databases_dir / f"relic_collection{suffix}.dat",
            'items': self.databases_dir / f"items{suffix}.dat",
            'etcitemgrp': self.databases_dir / f"etcitemgrp{suffix}.dat",
            'relic_xml': self.xml_files_dir / xml_folder / "RelicData.xml",
            'collection_xml': self.xml_files_dir / xml_folder / "RelicCollectionData.xml",
            'coupon_xml': self.xml_files_dir / xml_folder / "RelicCouponData.xml"
        }

    def run(self):
        try:
            updater = RelicXMLUpdater()
            paths = self.get_file_paths()
            
            if not hasattr(self, 'version'):
                self.version = "Main"                

            # VERIFICAÇÃO DE ARQUIVOS
            missing_files = []
            for key, path in paths.items():
                if not path.exists():
                    missing_files.append(f"{key}: {path.name}")
            
            if missing_files:
                raise FileNotFoundError(
                    f"Arquivos não encontrados ({self.version}):\n" + 
                    "\n".join(missing_files)
                )
            
            self.log.emit(f"📁 Processando versão: {self.version}")
            
            # 1. Carregar XMLs existentes
            self.log.emit("📁 Carregando XMLs existentes...")
            success = updater.load_existing_xmls(
                str(paths['relic_xml']), 
                str(paths['collection_xml']), 
                str(paths['coupon_xml'])
            )
            
            if not success:
                raise Exception("Falha ao carregar XMLs existentes")
            
            self.progress.emit(1, 9, "✓ XMLs carregados")
            
            # 2. Parsear DATs
            self.log.emit("📁 Parseando relic_data.dat...")
            relics = updater.parse_relics_main(str(paths['relic_main']))
            self.progress.emit(2, 9, f"✓ {len(relics)} relics carregadas")
            
            self.log.emit("📁 Parseando relic_collection.dat...")
            collections = updater.parse_collection(str(paths['relic_collection']))
            self.progress.emit(3, 9, f"✓ {len(collections)} collections carregadas")
            
            self.log.emit("📁 Parseando items.dat...")
            items_lookup = updater.parse_items_essence(str(paths['items']))
            self.progress.emit(4, 9, f"✓ {len(items_lookup)} items carregados")
            
            # 3. Parsear etcitemgrp (opcional)
            if paths['etcitemgrp'].exists():
                self.log.emit("📁 Parseando etcitemgrp.dat...")
                materials = updater.parse_etcitemgrp(str(paths['etcitemgrp']))
                self.progress.emit(5, 9, f"✓ {len(materials)} materiais carregados")
            else:
                self.log.emit("⏭️ etcitemgrp.dat não encontrado, usando filtros básicos")
                self.progress.emit(5, 9, "⏭️ etcitemgrp.dat não encontrado")
            
            # 4. Encontrar coupons
            self.log.emit("🔍 Buscando coupons existentes...")
            coupon_suggestions = updater.find_coupon_suggestions()
            self.progress.emit(6, 9, f"✓ {len(coupon_suggestions)} sugestões encontradas")
            
            # 5. Atualizar XMLs
            self.log.emit("⚙️ Atualizando RelicData.xml...")
            relic_result = updater.update_relic_data_xml(str(paths['relic_xml']))  # CORREÇÃO AQUI
            self.progress.emit(7, 9, "✓ RelicData.xml atualizado")
            
            self.log.emit("⚙️ Atualizando RelicCollectionData.xml...")
            collection_result = updater.update_collection_xml(str(paths['collection_xml']))  # CORREÇÃO AQUI
            self.progress.emit(8, 9, "✓ RelicCollectionData.xml atualizado")
            
            # 6. Ler conteúdo do coupon XML
            self.log.emit("⚙️ Preparando RelicCouponData.xml...")
            coupon_content = Path(paths['coupon_xml']).read_text(encoding='utf-8')  # CORREÇÃO AQUI
            self.progress.emit(9, 9, "✅ Todos os XMLs processados")
            
            self.log.emit("✅ Processo concluído com sucesso!")
            
            # Calcular estatísticas
            existing_relic_count = len(updater.existing_relics)
            new_relic_count = len(relics)
            added_relics = new_relic_count - existing_relic_count
            
            existing_collection_count = len(updater.existing_collections)
            new_collection_count = len(collections)
            added_collections = new_collection_count - existing_collection_count
            
            self.finished.emit({
                'relics': relics,
                'collections': collections,
                'items_lookup': items_lookup,
                'coupon_suggestions': coupon_suggestions,
                'updater': updater,
                'paths': {
                    'relic': str(paths['relic_xml']),
                    'collection': str(paths['collection_xml']),
                    'coupon': str(paths['coupon_xml'])
                },
                'contents': {
                    'relic': relic_result,
                    'collection': collection_result,
                    'coupon': coupon_content
                },
                'statistics': {
                    'existing_relics': existing_relic_count,
                    'new_relics': new_relic_count,
                    'added_relics': added_relics,
                    'existing_collections': existing_collection_count,
                    'new_collections': new_collection_count,
                    'added_collections': added_collections,
                    'total_items': len(items_lookup),
                    'coupon_matches': len(coupon_suggestions)
                },
                'version': self.version  # Adicionar versão aos resultados
            })
            
        except Exception as e:
            self.log.emit(f"❌ Erro na versão {getattr(self, 'version', 'N/A')}: {str(e)}")
            import traceback
            self.log.emit(traceback.format_exc())
            self.finished.emit({})


# ============================================================================
# MAIN UI (MESMA INTERFACE ANTERIOR - SÓ MUDOU O WORKER)
# ============================================================================
class RelicsTab(QWidget):
    def __init__(self, config):
        super().__init__()
        self.config = config or {}
        self.results = {}
        self.current_xml_path = None
        self.coupon_mapping = {}
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)

        # ===== SELEÇÃO DE VERSÃO =====
        version_group = QGroupBox("🎮 Versão do Jogo")
        version_layout = QHBoxLayout(version_group)
        
        version_layout.addWidget(QLabel("Versão:"))
        self.version_combo = QComboBox()
        self.version_combo.addItems(["Main", "Essence"])
        self.version_combo.currentTextChanged.connect(self.on_version_changed)
        version_layout.addWidget(self.version_combo)
        
        version_layout.addStretch()
        layout.addWidget(version_group)
        
        # ===== CONTROLES =====
        controls = QHBoxLayout()
        
        self.select_db_btn = QPushButton("📁 Selecionar Pasta databases/")
        self.select_xml_btn = QPushButton("📂 Selecionar Pasta XMLs/")
        self.update_btn = QPushButton("🔄 Atualizar XMLs")
        self.update_btn.setEnabled(False)
        self.update_btn.setStyleSheet("QPushButton:enabled { background: #0d7377; color: white; font-weight: bold; }")
        
        controls.addWidget(self.select_db_btn)
        controls.addWidget(self.select_xml_btn)
        controls.addStretch()
        controls.addWidget(self.update_btn)
        
        layout.addLayout(controls)
        
        # ===== STATUS DOS ARQUIVOS =====
        files_group = QGroupBox("📋 Status dos Arquivos")
        files_layout = QVBoxLayout(files_group)
        
        self.db_dir_label = QLabel("Pasta databases/: ❌ Não selecionada")
        self.xml_dir_label = QLabel("Pasta XMLs/: ❌ Não selecionada")
        self.main_file_label = QLabel("  ├─ relic_main: ⏳ Aguardando...")
        self.collection_file_label = QLabel("  ├─ relic_collection ⏳ Aguardando...")
        self.items_file_label = QLabel("  ├─ items: ⏳ Aguardando...")
        self.etcitems_file_label = QLabel("  └─ etcitems: ⏳ Aguardando...")
        
        for label in [self.db_dir_label, self.xml_dir_label, self.main_file_label, 
                     self.collection_file_label, self.items_file_label, self.etcitems_file_label]:
            files_layout.addWidget(label)
        
        layout.addWidget(files_group)
        
        # ===== PROGRESSO =====
        progress_group = QGroupBox("⚡ Progresso")
        progress_layout = QVBoxLayout(progress_group)
        
        self.progress_bar = QProgressBar()
        self.status_label = QLabel("Aguardando...")
        
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.status_label)
        
        layout.addWidget(progress_group)
        
        # ===== TABS =====
        self.tabs = QTabWidget()
        
        self.stats_tab = self.create_stats_tab()
        self.tabs.addTab(self.stats_tab, "📊 Estatísticas")
        
        self.relics_table_tab = self.create_relics_tab()
        self.tabs.addTab(self.relics_table_tab, "🏺 Relics")
        
        self.collections_tab = self.create_collections_tab()
        self.tabs.addTab(self.collections_tab, "📚 Collections")
        
        self.coupon_tab = self.create_coupon_tab()
        self.tabs.addTab(self.coupon_tab, "🎫 Coupon Matcher")
        
        self.xml_editor_tab = self.create_xml_editor_tab()
        self.tabs.addTab(self.xml_editor_tab, "✏️ XML Editor")
        
        layout.addWidget(self.tabs, 1)
        
        # ===== LOG =====
        log_group = QGroupBox("📝 Log")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setFont(QFont("Consolas", 9))
        
        log_layout.addWidget(self.log_text)
        layout.addWidget(log_group)
        
        # ===== CONEXÕES =====
        self.select_db_btn.clicked.connect(self.select_databases_folder)
        self.select_xml_btn.clicked.connect(self.select_xml_folder)
        self.update_btn.clicked.connect(self.start_update)
        
        # Variáveis
        self.databases_dir = None
        self.xml_files_dir = None
    
    def create_stats_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        stats_layout = QHBoxLayout()
        
        self.total_relics_label = QLabel("🏺 Relics: 0")
        self.total_collections_label = QLabel("📚 Collections: 0")
        self.changes_label = QLabel("📈 Mudanças: -")
        
        for label in [self.total_relics_label, self.total_collections_label, self.changes_label]:
            label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 10px;")
            stats_layout.addWidget(label)
        
        layout.addLayout(stats_layout)
        
        # Tabela de distribuição de grades
        self.grade_table = QTableWidget()
        self.grade_table.setColumnCount(3)
        self.grade_table.setHorizontalHeaderLabels(["Grade", "Count", "%"])
        self.grade_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        layout.addWidget(self.grade_table)
        
        # Estatísticas detalhadas
        self.stats_details = QTextEdit()
        self.stats_details.setReadOnly(True)
        self.stats_details.setMaximumHeight(100)
        self.stats_details.setFont(QFont("Consolas", 9))
        layout.addWidget(self.stats_details)
        
        return widget
    
    def create_relics_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("🔍 Buscar:"))
        
        self.relic_search = QLineEdit()
        self.relic_search.setPlaceholderText("ID, Grade...")
        filter_layout.addWidget(self.relic_search)
        
        filter_layout.addWidget(QLabel("Grade:"))
        self.grade_filter = QComboBox()
        self.grade_filter.addItem("Todos")
        filter_layout.addWidget(self.grade_filter)
        
        layout.addLayout(filter_layout)
        
        self.relics_table = QTableWidget()
        self.relics_table.setColumnCount(6)
        self.relics_table.setHorizontalHeaderLabels(["ID", "Grade", "Level", "Item ID", "Skills", "Status"])
        self.relics_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        
        layout.addWidget(self.relics_table)
        return widget
    
    def create_collections_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        self.collections_table = QTableWidget()
        self.collections_table.setColumnCount(5)
        self.collections_table.setHorizontalHeaderLabels(["ID", "Nome", "Categoria", "Option ID", "Relics"])
        self.collections_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        
        layout.addWidget(self.collections_table)
        
        details_group = QGroupBox("Detalhes da Collection")
        details_layout = QVBoxLayout(details_group)
        
        self.collection_details = QTextEdit()
        self.collection_details.setReadOnly(True)
        self.collection_details.setMaximumHeight(120)
        
        details_layout.addWidget(self.collection_details)
        layout.addWidget(details_group)
        
        self.collections_table.itemSelectionChanged.connect(self.show_collection_details)
        return widget
    
    def create_coupon_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        info_label = QLabel("🎫 Sugestões de Coupons (Baseado em XML existente)")
        info_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 10px;")
        layout.addWidget(info_label)
        
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("🔍 Filtrar por Relic ID:"))
        
        self.coupon_filter = QLineEdit()
        self.coupon_filter.setPlaceholderText("Digite Relic ID...")
        self.coupon_filter.textChanged.connect(self.filter_coupon_table)
        filter_layout.addWidget(self.coupon_filter)
        
        self.show_matched_only = QCheckBox("Mostrar apenas com sugestões")
        self.show_matched_only.stateChanged.connect(self.filter_coupon_table)
        filter_layout.addWidget(self.show_matched_only)
        
        filter_layout.addStretch()
        
        self.export_coupon_btn = QPushButton("💾 Atualizar RelicCouponData.xml")
        self.export_coupon_btn.clicked.connect(self.regenerate_coupon_xml)
        self.export_coupon_btn.setStyleSheet("background: #2a9d8f; color: white; font-weight: bold;")
        filter_layout.addWidget(self.export_coupon_btn)
        
        layout.addLayout(filter_layout)
        
        self.coupon_table = QTableWidget()
        self.coupon_table.setColumnCount(7)
        self.coupon_table.setHorizontalHeaderLabels([
            "Relic ID", "Grade", "Doll Name", "Item ID", 
            "Coupon Match", "Item ID", "Selecionar"
        ])
        self.coupon_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.coupon_table.itemClicked.connect(self.show_coupon_details)
        
        layout.addWidget(self.coupon_table)
        
        details_group = QGroupBox("📋 Detalhes do Coupon")
        details_layout = QVBoxLayout(details_group)
        
        self.coupon_details = QTextEdit()
        self.coupon_details.setReadOnly(True)
        self.coupon_details.setMaximumHeight(150)
        self.coupon_details.setFont(QFont("Consolas", 9))
        
        details_layout.addWidget(self.coupon_details)
        layout.addWidget(details_group)
        
        return widget
    
    def create_xml_editor_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        file_select_layout = QHBoxLayout()
        file_select_layout.addWidget(QLabel("Arquivo XML:"))
        
        self.xml_file_combo = QComboBox()
        self.xml_file_combo.addItems(["RelicData.xml", "RelicCollectionData.xml", "RelicCouponData.xml"])
        self.xml_file_combo.currentTextChanged.connect(self.load_xml_for_edit)
        file_select_layout.addWidget(self.xml_file_combo)
        
        self.reload_xml_btn = QPushButton("🔄 Recarregar")
        self.reload_xml_btn.clicked.connect(self.load_xml_for_edit)
        file_select_layout.addWidget(self.reload_xml_btn)
        
        self.save_xml_btn = QPushButton("💾 Salvar Alterações")
        self.save_xml_btn.clicked.connect(self.save_xml_changes)
        self.save_xml_btn.setStyleSheet("background: #2a9d8f; color: white; font-weight: bold;")
        file_select_layout.addWidget(self.save_xml_btn)
        
        file_select_layout.addStretch()
        layout.addLayout(file_select_layout)
        
        self.xml_editor = QTextEdit()
        self.xml_editor.setFont(QFont("Consolas", 10))
        self.xml_editor.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        
        self.xml_highlighter = XMLHighlighter(self.xml_editor.document())
        
        layout.addWidget(self.xml_editor)
        
        self.xml_info_label = QLabel("Selecione um arquivo XML para editar")
        self.xml_info_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.xml_info_label)
        
        return widget
    
    # ===== MÉTODOS DA UI =====
    
    def select_databases_folder(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Selecionar Pasta databases/",
            "",
            QFileDialog.Option.ShowDirsOnly
        )
        
        if directory:
            self.databases_dir = Path(directory)
            self.db_dir_label.setText(f"Pasta databases/: ✅ {directory}")
            
            # Verificar arquivos para AMBAS versões
            files_to_check = {
                'Main': {
                    'relic': 'relic_main_main.dat',
                    'collection': 'relic_collection_main.dat', 
                    'items': 'items_main.dat',
                    'etcitemgrp': 'etcitemgrp_main.dat'
                },
                'Essence': {
                    'relic': 'relic_main_essence.dat',
                    'collection': 'relic_collection_essence.dat',
                    'items': 'items_essence.dat',
                    'etcitemgrp': 'etcitemgrp_essence.dat'
                }
            }
            
            # Atualizar labels baseado na versão selecionada
            self.update_file_labels()
            
            # Log das versões disponíveis
            available_versions = []
            
            for version_name, files in files_to_check.items():
                has_all_files = all(
                    (self.databases_dir / fname).exists()
                    for fname in files.values()
                )
                
                if has_all_files:
                    available_versions.append(version_name)
            
            if available_versions:
                self.log(f"✅ Versões disponíveis: {', '.join(available_versions)}")
                
                # Se só tem uma versão, selecionar automaticamente
                if len(available_versions) == 1:
                    self.version_combo.setCurrentText(available_versions[0])
                    self.log(f"📁 Versão {available_versions[0]} selecionada automaticamente")
            else:
                self.log("⚠️ Nenhuma versão completa encontrada")
            
            self.check_ready()

    def update_file_labels(self):
        """Atualiza os labels dos arquivos baseado na versão selecionada"""
        if not self.databases_dir:
            return
        
        version = self.version_combo.currentText()
        
        files = {
            'Main': {
                'relic': 'relic_main_main.dat',
                'collection': 'relic_collection_main.dat',
                'items': 'items_main.dat',
                'etcitemgrp': 'etcitemgrp_main.dat'
            },
            'Essence': {
                'relic': 'relic_main_essence.dat',
                'collection': 'relic_collection_essence.dat',
                'items': 'items_essence.dat',
                'etcitemgrp': 'etcitemgrp_essence.dat'
            }
        }[version]
        
        # Atualizar labels
        self.main_file_label.setText(
            f"  ├─ {files['relic']}: {'✅ Encontrado' if (self.databases_dir / files['relic']).exists() else '❌ Não encontrado'}"
        )
        self.collection_file_label.setText(
            f"  ├─ {files['collection']}: {'✅ Encontrado' if (self.databases_dir / files['collection']).exists() else '❌ Não encontrado'}"
        )
        self.items_file_label.setText(
            f"  ├─ {files['items']}: {'✅ Encontrado' if (self.databases_dir / files['items']).exists() else '❌ Não encontrado'}"
        )
        
        # etcitemgrp é opcional
        etcitemgrp_path = self.databases_dir / files['etcitemgrp']
        if etcitemgrp_path.exists():
            self.etcitems_file_label.setText(
                f"  └─ {files['etcitemgrp']}: ✅ Encontrado (opcional)"
            )
        else:
            self.etcitems_file_label.setText(
                f"  └─ {files['etcitemgrp']}: ⚠️ Não encontrado (usará filtros básicos)"
            )
    
    def select_xml_folder(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Selecionar Pasta com XMLs",
            "",
            QFileDialog.Option.ShowDirsOnly
        )
        
        if directory:
            self.xml_files_dir = Path(directory)
            
            # Verificar se tem ambas as pastas
            has_main = (self.xml_files_dir / "relics_main").exists()
            has_essence = (self.xml_files_dir / "relics_essence").exists()
            
            available_folders = []
            if has_main:
                available_folders.append("relics_main")
            if has_essence:
                available_folders.append("relics_essence")
            
            if available_folders:
                self.xml_dir_label.setText(f"Pasta XMLs/: ✅ {directory}")
                self.log(f"📁 Pastas XML encontradas: {', '.join(available_folders)}")
                
                # Se só tem uma, selecionar versão correspondente
                if has_main and not has_essence:
                    self.version_combo.setCurrentText("Main")
                elif has_essence and not has_main:
                    self.version_combo.setCurrentText("Essence")
            else:
                self.xml_dir_label.setText(f"Pasta XMLs/: ❌ Nenhuma pasta 'relics_' encontrada")
                self.log("⚠️ Nenhuma pasta 'relics_main' ou 'relics_essence' encontrada")
            
            self.check_ready()
    
    def check_ready(self):
        if self.databases_dir and self.xml_files_dir:
            version = self.version_combo.currentText()
            
            # Mapeamento de versões - USE O MESMO DO SEU on_version_changed
            paths = {
                'Main': {
                    'dat': ['relic_main_main.dat', 'relic_collection_main.dat', 'items_main.dat'],
                    'xml_folder': 'relics_main',
                    'xml_files': ['RelicData.xml', 'RelicCollectionData.xml', 'RelicCouponData.xml']
                },
                'Essence': {
                    'dat': ['relic_main_essence.dat', 'relic_collection_essence.dat', 'items_essence.dat'],
                    'xml_folder': 'relics_essence', 
                    'xml_files': ['RelicData.xml', 'RelicCollectionData.xml', 'RelicCouponData.xml']
                }
            }
            
            v = paths[version]
            
            # 1. Verificar arquivos DAT
            dat_files_ok = all(
                (self.databases_dir / f).exists() 
                for f in v['dat']
            )
            
            # 2. Verificar pasta XML
            xml_folder = self.xml_files_dir / v['xml_folder']
            xml_folder_exists = xml_folder.exists()
            
            # 3. Verificar arquivos XML DENTRO da pasta
            xml_files_ok = False
            if xml_folder_exists:
                xml_files_ok = all(
                    (xml_folder / xml_file).exists()
                    for xml_file in v['xml_files']
                )
            
            # Atualizar botão
            if dat_files_ok and xml_files_ok:
                self.update_btn.setEnabled(True)
                self.log(f"✅ Versão {version} pronta para atualizar!")
            else:
                self.update_btn.setEnabled(False)
                
                if not dat_files_ok:
                    self.log(f"⚠️ Alguns arquivos DAT da versão {version} não foram encontrados")
                
                if not xml_folder_exists:
                    self.log(f"⚠️ Pasta '{v['xml_folder']}' não encontrada na versão {version}")
                elif not xml_files_ok:
                    self.log(f"⚠️ Alguns arquivos XML na pasta '{v['xml_folder']}' não foram encontrados")
                    
                    # Mostrar quais arquivos estão faltando
                    missing_files = []
                    for xml_file in v['xml_files']:
                        if not (xml_folder / xml_file).exists():
                            missing_files.append(xml_file)
                    
                    if missing_files:
                        self.log(f"   Faltando: {', '.join(missing_files)}")
        else:
            self.update_btn.setEnabled(False)
    
    def start_update(self):

            if not hasattr(self, 'worker') or not self.worker.isRunning():
                version = self.version_combo.currentText()  # "Main" ou "Essence"
                
                self.worker = XMLUpdaterWorker(
                    str(self.databases_dir), 
                    str(self.xml_files_dir),
                    version
                )
            
            self.worker.log.connect(self.log)
            self.worker.progress.connect(self.update_progress)
            self.worker.finished.connect(self.update_finished)
            
            self.worker.start()
            self.update_btn.setEnabled(False)
            self.select_db_btn.setEnabled(False)
            self.select_xml_btn.setEnabled(False)

    def on_version_changed(self, version):
        """Atualiza os labels quando a versão muda"""
        if not self.databases_dir or not self.xml_files_dir:
            return
        
        paths = {
            'Main': {
                'relic': 'relic_main_main.dat',
                'collection': 'relic_collection_main.dat',
                'items': 'items_main.dat',
                'etcitemgrp': 'etcitemgrp_main.dat',
                'xml_folder': 'relics_main'
            },
            'Essence': {
                'relic': 'relic_main_essence.dat',
                'collection': 'relic_collection_essence.dat',
                'items': 'items_essence.dat',
                'etcitemgrp': 'etcitemgrp_essence.dat',
                'xml_folder': 'relics_essence'
            }
        }
        
        v = paths[version]
        
        # Atualizar labels
        self.main_file_label.setText(
            f"  ├─ {v['relic']}: {'✅ Encontrado' if (self.databases_dir / v['relic']).exists() else '❌ Não encontrado'}"
        )
        self.collection_file_label.setText(
            f"  ├─ {v['collection']}: {'✅ Encontrado' if (self.databases_dir / v['collection']).exists() else '❌ Não encontrado'}"
        )
        self.items_file_label.setText(
            f"  └─ {v['items']}: {'✅ Encontrado' if (self.databases_dir / v['items']).exists() else '❌ Não encontrado'}"
        )
        
        # Verificar pasta XML
        xml_folder = self.xml_files_dir / v['xml_folder']
        if xml_folder.exists():
            self.xml_dir_label.setText(f"Pasta XMLs/: ✅ {xml_folder}")
            self.log(f"📁 Versão {version} selecionada")
        else:
            self.xml_dir_label.setText(f"Pasta XMLs/: ❌ {v['xml_folder']} não encontrada")
        
        self.check_ready()
    
    def update_progress(self, current, total, status):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(status)
    
    def update_finished(self, results):
        self.results = results
        self.update_btn.setEnabled(True)
        self.select_db_btn.setEnabled(True)
        self.select_xml_btn.setEnabled(True)
        
        if results:
            # DEBUG: Verificar o que chegou
            print(f"DEBUG - Relics recebidas: {len(results.get('relics', []))}")
            print(f"DEBUG - Collections recebidas: {len(results.get('collections', []))}")
            print(f"DEBUG - Items lookup: {len(results.get('items_lookup', {}))}")
            
            # Atualizar UI
            self.update_stats()
            self.update_relics_table()
            self.update_collections_table()
            self.update_coupon_table()
            self.log("✅ Atualização concluída! XMLs prontos para edição.")
            self.load_xml_for_edit()
        else:
            self.log("❌ Nenhum resultado recebido do processamento")
    
    def update_stats(self):
        if not self.results:
            self.log("❌ Nenhum resultado para mostrar estatísticas")
            return
        
        stats = self.results.get('statistics', {})
        relics = self.results.get('relics', [])
        collections = self.results.get('collections', [])
        
        print(f"DEBUG update_stats - Relics: {len(relics)}, Collections: {len(collections)}")
        
        # Atualizar labels
        self.total_relics_label.setText(f"🏺 Relics: {len(relics)}")
        self.total_collections_label.setText(f"📚 Collections: {len(collections)}")
        
        if stats:
            changes_text = f"📈 Mudanças: +{stats.get('added_relics', 0)} relics, +{stats.get('added_collections', 0)} collections"
            self.changes_label.setText(changes_text)
        
        # Atualizar tabela de grades
        grade_counts = {}
        for relic in relics:
            grade = relic.get('grade', 'UNKNOWN')
            grade_counts[grade] = grade_counts.get(grade, 0) + 1
        
        self.grade_table.setRowCount(len(grade_counts))
        for i, (grade, count) in enumerate(sorted(grade_counts.items())):
            percentage = (count / len(relics) * 100) if relics else 0
            
            self.grade_table.setItem(i, 0, QTableWidgetItem(grade))
            self.grade_table.setItem(i, 1, QTableWidgetItem(str(count)))
            self.grade_table.setItem(i, 2, QTableWidgetItem(f"{percentage:.1f}%"))
        
        # Atualizar filtro de grades
        grades = sorted(grade_counts.keys())
        self.grade_filter.clear()
        self.grade_filter.addItem("Todos")
        self.grade_filter.addItems(grades)
        
        # Detalhes
        details = f"""📊 Estatísticas:
    • Total Relics: {len(relics)}
    • Total Collections: {len(collections)}
    • Grades diferentes: {len(grade_counts)}
    """
        
        if stats:
            details += f"""• Relics adicionadas: {stats.get('added_relics', 0)}
    • Collections adicionadas: {stats.get('added_collections', 0)}
    """
        
        self.stats_details.setText(details)
    
    def update_relics_table(self):
        relics = self.results.get('relics', [])
        print(f"DEBUG update_relics_table: {len(relics)} relics")
        
        if not relics:
            self.log("⚠️ Nenhuma relic para exibir na tabela")
            self.relics_table.setRowCount(0)
            return
        
        self.relics_table.setRowCount(len(relics))
        
        for i, relic in enumerate(relics):
            # ID
            self.relics_table.setItem(i, 0, QTableWidgetItem(str(relic.get('id', ''))))
            
            # Grade
            self.relics_table.setItem(i, 1, QTableWidgetItem(relic.get('grade', '')))
            
            # Level
            self.relics_table.setItem(i, 2, QTableWidgetItem(str(relic.get('level', 1))))
            
            # Item ID (da Doll)
            item_id = relic.get('item_id', '')
            self.relics_table.setItem(i, 3, QTableWidgetItem(str(item_id)))
            
            # Skills
            skills = relic.get('skills', [])
            if skills:
                skill_text = ', '.join([f"S{s.get('id', 0)}" for s in skills])
            else:
                skill_text = "Nenhum"
            self.relics_table.setItem(i, 4, QTableWidgetItem(skill_text))
            
            # Status
            existing_ids = []
            if 'updater' in self.results and hasattr(self.results['updater'], 'existing_relics'):
                existing_ids = list(self.results['updater'].existing_relics.keys())
            
            status = "🆕 Nova" if relic['id'] not in existing_ids else "✅ Existente"
            self.relics_table.setItem(i, 5, QTableWidgetItem(status))
        
        self.log(f"📋 Tabela de relics atualizada: {len(relics)} itens")
    
    def update_collections_table(self):
        collections = self.results.get('collections', [])
        print(f"DEBUG update_collections_table: {len(collections)} collections")
        
        if not collections:
            self.log("⚠️ Nenhuma collection para exibir na tabela")
            self.collections_table.setRowCount(0)
            return
        
        self.collections_table.setRowCount(len(collections))
        
        for i, col in enumerate(collections):
            # ID
            self.collections_table.setItem(i, 0, QTableWidgetItem(str(col.get('id', ''))))
            
            # Nome
            self.collections_table.setItem(i, 1, QTableWidgetItem(col.get('name', '')))
            
            # Categoria
            self.collections_table.setItem(i, 2, QTableWidgetItem(str(col.get('category', ''))))
            
            # Option ID
            self.collections_table.setItem(i, 3, QTableWidgetItem(str(col.get('optionId', ''))))
            
            # Número de relics
            relics_count = len(col.get('relics', []))
            self.collections_table.setItem(i, 4, QTableWidgetItem(str(relics_count)))
        
        self.log(f"📚 Tabela de collections atualizada: {len(collections)} itens") 

    def update_coupon_table(self):
        coupon_suggestions = self.results.get('coupon_suggestions', {})
        print(f"DEBUG update_coupon_table: {len(coupon_suggestions)} sugestões (APENAS mesma grade)")
        
        if not coupon_suggestions:
            # Verificar quantas relics existem vs quantas têm cupons
            total_relics = len(self.results.get('relics', []))
            
            if 'updater' in self.results:
                updater = self.results['updater']
                relics_with_coupons = len(updater.existing_simple_coupons)
                
                relics_without_any_match = total_relics - relics_with_coupons - len(coupon_suggestions)
                
                self.log(f"🎫 {relics_with_coupons}/{total_relics} relics já têm cupons")
                
                if relics_without_any_match > 0:
                    self.log(f"📋 {relics_without_any_match} relics não têm cupons da mesma grade disponíveis")
                else:
                    self.log("✅ Todas as relics têm cupons ou já estão no XML!")
            else:
                self.log("Nenhuma sugestão encontrada")
            
            self.coupon_table.setRowCount(0)
            return
        
        # Configurar tabela (agora sem coluna de material separada já que todos são válidos)
        self.coupon_table.setColumnCount(7)
        self.coupon_table.setHorizontalHeaderLabels([
            "Relic ID", "Grade", "Doll Name", "Item ID", 
            "Coupon Match", "Coupon ID", "Selecionar"
        ])
        
        self.coupon_table.setRowCount(len(coupon_suggestions))
        
        row = 0
        for relic_id, suggestion in sorted(coupon_suggestions.items()):
            # Relic ID
            self.coupon_table.setItem(row, 0, QTableWidgetItem(str(relic_id)))
            
            # Grade da relic
            grade = suggestion.get('grade', 'UNKNOWN')
            self.coupon_table.setItem(row, 1, QTableWidgetItem(grade))
            
            # Nome da Doll
            self.coupon_table.setItem(row, 2, QTableWidgetItem(suggestion.get('doll_name', '')))
            
            # Item ID da Doll
            self.coupon_table.setItem(row, 3, QTableWidgetItem(str(suggestion.get('item_id', ''))))
            
            # Matches de coupons (sempre da mesma grade agora)
            matches = suggestion.get('matches', [])
            if matches:
                # Primeiro match (melhor match)
                coupon_id, coupon_name, similarity = matches[0]
                
                # Nome do coupon
                coupon_item = QTableWidgetItem(coupon_name)
                coupon_item.setToolTip(f"🎯 Cupom da mesma grade ({similarity*100:.0f}% confiança)")
                coupon_item.setForeground(QColor("#4CAF50"))  # Verde = válido
                self.coupon_table.setItem(row, 4, coupon_item)
                
                # Item ID do coupon
                self.coupon_table.setItem(row, 5, QTableWidgetItem(str(coupon_id)))
                
                # Botão de seleção
                select_btn = QPushButton("✓ Usar")
                select_btn.setToolTip(f"Selecionar este cupom para Relic {relic_id}")
                
                # Conectar o clique
                select_btn.clicked.connect(
                    lambda checked, rid=relic_id, cid=coupon_id, g=grade: 
                    self.select_coupon(rid, cid, g)
                )
                
                # Botão VERDE (todos são válidos agora)
                select_btn.setStyleSheet("""
                    QPushButton {
                        background: #4CAF50; 
                        color: white; 
                        font-weight: bold;
                        border: 2px solid #2E7D32;
                    }
                    QPushButton:hover {
                        background: #388E3C;
                    }
                """)
                
                self.coupon_table.setCellWidget(row, 6, select_btn)
            
            row += 1
        
        # Ajustar tamanho das colunas
        self.coupon_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)  # Nome do cupom expande
        
        # Log final
        self.log(f"🎫 {len(coupon_suggestions)} relics com cupons da MESMA grade encontrados")
        
        # Se tiver updater, mostrar estatísticas
        if 'updater' in self.results:
            updater = self.results['updater']
            total_without_coupons = len([r for r in self.results.get('relics', []) 
                                    if str(r['id']) not in updater.existing_simple_coupons])
            without_matches = total_without_coupons - len(coupon_suggestions)
            
            if without_matches > 0:
                self.log(f"📋 {without_matches} relics não têm cupons disponíveis na mesma grade")    

    def select_coupon(self, relic_id, coupon_id, grade):
        """Marca um coupon para ser adicionado ao XML"""
        # Verificar se já existe
        if relic_id in self.coupon_mapping:
            existing = self.coupon_mapping[relic_id]
            reply = QMessageBox.question(
                self,
                "Coupon já selecionado",
                f"Relic {relic_id} já tem coupon {existing['coupon_id']} selecionado.\n"
                f"Deseja substituir por coupon {coupon_id}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
        
        # Obter nome do coupon
        coupon_name = ""
        if 'items_lookup' in self.results:
            coupon_name = self.results['items_lookup'].get(int(coupon_id), "")
        
        # Armazenar
        self.coupon_mapping[relic_id] = {
            'coupon_id': coupon_id,
            'grade': grade,
            'coupon_name': coupon_name
        }
        
        self.log(f"✓ Coupon selecionado: Relic {relic_id} → {coupon_name or coupon_id}")
        
        # Marcar visualmente na tabela
        self.mark_coupon_selected_in_table(relic_id, coupon_id)

    def mark_coupon_selected_in_table(self, relic_id, coupon_id):
        """Marca visualmente o coupon selecionado na tabela"""
        for row in range(self.coupon_table.rowCount()):
            item = self.coupon_table.item(row, 0)  # Coluna do Relic ID
            if item and int(item.text()) == relic_id:
                # Mudar o botão
                btn = self.coupon_table.cellWidget(row, 6)
                if btn:
                    btn.setText("✅ Selecionado")
                    btn.setStyleSheet("background: #4CAF50; color: white;")
                
                # Destacar linha
                for col in range(self.coupon_table.columnCount()):
                    item = self.coupon_table.item(row, col)
                    if item:
                        item.setBackground(QColor("#E8F5E9"))
                break

    def regenerate_coupon_xml(self):
        if not self.coupon_mapping:
            QMessageBox.warning(
                self,
                "Aviso",
                "Nenhum coupon selecionado!\n\nSelecione coupons clicando em '✓ Usar' na tabela."
            )
            return
        
        try:
            updater = self.results.get('updater')
            if not updater:
                raise Exception("Updater não disponível")
            
            coupon_xml_path = self.results['paths']['coupon']
            
            # DEBUG
            print(f"\n=== DEBUG COUPON MAPPING ===")
            print(f"Coupons selecionados: {len(self.coupon_mapping)}")
            for relic_id, data in self.coupon_mapping.items():
                print(f"  Relic {relic_id} -> Coupon {data['coupon_id']} ({data['grade']})")
            
            # Chamar o método CORRETAMENTE
            result = updater.generate_coupon_xml(coupon_xml_path, self.coupon_mapping)
            
            # Atualizar conteúdo em cache
            content = Path(coupon_xml_path).read_text(encoding='utf-8')
            self.results['contents']['coupon'] = content
            
            # Log e mensagem
            self.log(f"💾 {result}")
            QMessageBox.information(
                self,
                "Sucesso",
                f"RelicCouponData.xml atualizado!\n\n{result}"
            )
            
            # Recarregar se estiver na aba certa
            if self.xml_file_combo.currentText() == "RelicCouponData.xml":
                self.load_xml_for_edit()
            
            # Limpar seleções
            self.coupon_mapping = {}
            
            # Atualizar tabela para mostrar que já foram processados
            self.update_coupon_table()
                
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao atualizar XML:\n{str(e)}")
            self.log(f"❌ Erro: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def filter_coupon_table(self):
        search_text = self.coupon_filter.text().lower()
        show_matched = self.show_matched_only.isChecked()
        
        for row in range(self.coupon_table.rowCount()):
            show = True
            
            if search_text:
                relic_id = self.coupon_table.item(row, 0).text()
                doll_name = self.coupon_table.item(row, 2).text().lower()
                show = search_text in relic_id or search_text in doll_name
            
            if show and show_matched:
                match_item = self.coupon_table.item(row, 4)
                show = match_item and "❌" not in match_item.text()
            
            self.coupon_table.setRowHidden(row, not show)
    
    def show_coupon_details(self, item):
        row = item.row()
        relic_id_item = self.coupon_table.item(row, 0)
        if not relic_id_item:
            return
        
        relic_id = int(relic_id_item.text())
        suggestions = self.results.get('coupon_suggestions', {})
        
        if relic_id not in suggestions:
            return
        
        suggestion = suggestions[relic_id]
        
        details = f"""🏺 Relic ID: {relic_id}
        📦 Item ID: {suggestion['item_id']}
        🎭 Nome Original: {suggestion['original_name']}
        ✨ Nome Extraído: {suggestion['doll_name']}

        🎫 Coupons Correspondentes:
        """
        
        for i, (coupon_id, coupon_name, similarity) in enumerate(suggestion['matches'], 1):
            # Adicionar indicador visual de confiança
            if similarity == 1.0:
                confidence = "🎯 Match Perfeito"
            elif similarity > 0.8:
                confidence = "✅ Alta confiança"
            elif similarity > 0.6:
                confidence = "⚠️ Média confiança"
            else:
                confidence = "❓ Baixa confiança"
            
            details += f"\n{i}. [ID: {coupon_id}] {coupon_name}\n"
            details += f"   {confidence} ({similarity*100:.0f}% similar)\n"
        
        self.coupon_details.setText(details)
    
    def show_collection_details(self):
        selected = self.collections_table.selectedItems()
        if not selected:
            return
        
        row = selected[0].row()
        collections = self.results.get('collections', [])
        if row >= len(collections):
            return
        
        col = collections[row]
        
        details = f"""📚 Collection: {col.get('name', 'N/A')}
        🆔 ID: {col.get('id')}
        🏷️ Categoria: {col.get('category')}
        🎯 Option ID: {col.get('optionId')}

        🏺 Relics Necessárias ({len(col.get('relics', []))}):
        """
        for relic in col.get('relics', []):
            details += f"  • Relic ID: {relic.get('id')}, Enchant Level: {relic.get('enchantLevel')}\n"
        
        self.collection_details.setText(details)
    
    #def select_coupon(self, relic_id, coupon_id, grade):
    #    self.coupon_mapping[relic_id] = {
    #        'coupon_id': coupon_id,
    #        'grade': grade
    #    }
    #    self.log(f"✓ Coupon {coupon_id} selecionado para Relic {relic_id} ({grade})")
    
    #def regenerate_coupon_xml(self):
    #    if not self.coupon_mapping:
    #        QMessageBox.warning(
    #            self,
    #            "Aviso",
    #            "Nenhum coupon selecionado!\n\nSelecione coupons clicando em '✓ Usar' na tabela."
    #        )
    #        return
    #    
    #    try:
    #        updater = self.results.get('updater')
    #        if not updater:
    #            raise Exception("Updater não disponível")
    #        
    #        coupon_xml_path = self.results['paths']['coupon']
    #        updater.generate_coupon_xml(coupon_xml_path, self.coupon_mapping)
    #        
    #        content = Path(coupon_xml_path).read_text(encoding='utf-8')
    #        self.results['contents']['coupon'] = content
    #        
    #        self.log(f"💾 RelicCouponData.xml atualizado com {len(self.coupon_mapping)} mapeamentos!")
    #        QMessageBox.information(
    #            self,
    #            "Sucesso",
    #            f"RelicCouponData.xml atualizado com sucesso!\n\n{len(self.coupon_mapping)} coupons mapeados."
    #        )
    #        
    #        if self.xml_file_combo.currentText() == "RelicCouponData.xml":
    #            self.load_xml_for_edit()
    #        
    #    except Exception as e:
    #        QMessageBox.critical(self, "Erro", f"Erro ao atualizar XML:\n{str(e)}")
    #        self.log(f"❌ Erro: {str(e)}")
    
    def load_xml_for_edit(self):
        if not self.results or 'paths' not in self.results:
            self.xml_editor.clear()
            self.xml_info_label.setText("⚠️ Atualize os XMLs primeiro!")
            return
        
        xml_name = self.xml_file_combo.currentText()
        paths = self.results['paths']
        
        key_map = {
            'RelicData.xml': 'relic',
            'RelicCollectionData.xml': 'collection',
            'RelicCouponData.xml': 'coupon'
        }
        
        key = key_map.get(xml_name)
        if not key or key not in paths:
            return
        
        self.current_xml_path = paths[key]
        
        try:
            content = Path(self.current_xml_path).read_text(encoding='utf-8')
            self.xml_editor.setPlainText(content)
            
            file_size = Path(self.current_xml_path).stat().st_size
            line_count = content.count('\n')
            
            self.xml_info_label.setText(
                f"📄 {xml_name} | 📏 {file_size:,} bytes | 📝 {line_count} linhas | 📂 {self.current_xml_path}"
            )
            self.log(f"📄 Carregado: {xml_name}")
            
        except Exception as e:
            self.log(f"❌ Erro ao carregar XML: {str(e)}")
            self.xml_editor.clear()
    
    def save_xml_changes(self):
        if not self.current_xml_path:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo XML carregado!")
            return
        
        content = self.xml_editor.toPlainText()
        
        try:
            ET.fromstring(content)
        except ET.ParseError as e:
            QMessageBox.critical(
                self,
                "Erro de XML",
                f"O XML contém erros de sintaxe:\n\n{str(e)}\n\nCorrija os erros antes de salvar."
            )
            return
        
        reply = QMessageBox.question(
            self,
            "Confirmar Salvamento",
            f"Salvar alterações em:\n{self.current_xml_path}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                Path(self.current_xml_path).write_text(content, encoding='utf-8')
                self.log(f"💾 Salvo: {Path(self.current_xml_path).name}")
                QMessageBox.information(self, "Sucesso", "Arquivo salvo com sucesso!")
                
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Erro ao salvar:\n{str(e)}")
                self.log(f"❌ Erro ao salvar: {str(e)}")
    
    def log(self, message):
        self.log_text.append(message)
        scrollbar = self.log_text.verticalScrollBar()
        if scrollbar is not None:
            scrollbar.setValue(scrollbar.maximum())