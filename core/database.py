import json
import re
from typing import Dict, Optional

class DatabaseManager:
    # ✅ Variáveis de classe (compartilhadas entre instâncias)
    ITEM_INDEX: dict[int, str] = {}
    ITEM_INDEX_ESSENCE: dict[int, str] = {}
    SKILL_INDEX: dict[int, list[str]] = {}
    SKILL_INDEX_ESSENCE: dict[int, list[str]] = {}
    SKILLGRP_INDEX: dict[int, str] = {}
    SKILLGRP_INDEX_ESSENCE: dict[int, str] = {}
    
    def __init__(self, config):
        self.config = config
        self.config_file = self.config.config_file
        self.lock_file = self.config.lock_file
        self.extractable_types = {}
        self.config.load_config()
        
        # ✅ Carregar índices se ainda não foram carregados
        self._ensure_indexes_loaded()
    
    def _ensure_indexes_loaded(self):
        """Carrega os índices apenas uma vez (lazy loading)"""
        if not DatabaseManager.ITEM_INDEX:
            DatabaseManager.ITEM_INDEX = self.build_item_index('databases/items_main.dat')
        
        if not DatabaseManager.ITEM_INDEX_ESSENCE:
            DatabaseManager.ITEM_INDEX_ESSENCE = self.build_item_index('databases/items_essence.dat')
        
        if not DatabaseManager.SKILL_INDEX:
            DatabaseManager.SKILL_INDEX = self.build_skill_index('databases/skills_main.dat')
        
        if not DatabaseManager.SKILL_INDEX_ESSENCE:
            DatabaseManager.SKILL_INDEX_ESSENCE = self.build_skill_index('databases/skills_essence.dat')

        if not DatabaseManager.SKILLGRP_INDEX:
            DatabaseManager.SKILLGRP_INDEX = self.build_skillgrp_index('databases/skillgrp_main.dat')
        
        if not DatabaseManager.SKILLGRP_INDEX_ESSENCE:
            DatabaseManager.SKILLGRP_INDEX_ESSENCE = self.build_skillgrp_index('databases/skillgrp_essence.dat')

    @staticmethod
    def build_item_index(dat_file: str) -> dict[int, str]: 
        """Constrói índice de items a partir do .dat"""
        index = {}
        try:
            with open(dat_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if ('item_name_begin' in line
                        and 'id=' in line
                        and 'name=[' in line
                        and 'additionalname=[' in line):

                        try:
                            item_id = int(line.split("id=")[1].split()[0])
                        except:
                            continue

                        # name=[...]
                        n1 = line.find('name=[') + 6
                        n2 = line.find(']', n1)
                        name = line[n1:n2] if n2 != -1 else ''

                        # additionalname=[...]
                        a1 = line.find('additionalname=[') + len('additionalname=[')
                        a2 = line.find(']', a1)
                        add = line[a1:a2] if a2 != -1 else ''

                        # montar nome final
                        if add:
                            full_name = f"{name} - {add}"
                        else:
                            full_name = name

                        index[item_id] = full_name
        except FileNotFoundError:
            print(f"⚠️ Arquivo não encontrado: {dat_file}")
        except Exception as e:
            print(f"⚠️ Erro ao carregar {dat_file}: {e}")
        
        return index
    
    @staticmethod
    def build_skill_index(dat_file: str) -> dict[int, list[str]]:
        """Constrói índice de skills a partir do .dat"""
        index = {}
        try:
            with open(dat_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if 'skill_begin' in line and 'skill_id=' in line and 'name=[' in line and 'icon=[' in line:
                        try:
                            skill_id = int(line.split("skill_id=")[1].split()[0])
                        except:
                            continue
                        
                        # Extrai o nome
                        n1 = line.find('name=[') + 6
                        n2 = line.find(']', n1)
                        name = line[n1:n2] if n2 != -1 else ''
                        
                        # Extrai o ícone
                        a1 = line.find('icon=[') + len('icon=[')
                        a2 = line.find(']', a1)
                        icon = line[a1:a2] if a2 != -1 else ''
                        
                        # Armazena ambos
                        index[skill_id] = [name, icon]
        
        except FileNotFoundError:
            print(f"Arquivo {dat_file} não encontrado")
        
        return index
    
    @staticmethod
    def build_skillgrp_index(dat_file: str) -> dict[int, str]:
        """Constrói índice de ícones de skills a partir do skillgrp.dat"""
        index = {}
        try:
            with open(dat_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if 'skill_begin' in line and 'skill_id=' in line and 'icon=[' in line:
                        try:
                            skill_id = int(line.split("skill_id=")[1].split()[0])
                        except:
                            continue
                        
                        # Extrai o ícone
                        a1 = line.find('icon=[') + len('icon=[')
                        a2 = line.find(']', a1)
                        icon = line[a1:a2] if a2 != -1 else ''
                        
                        if icon:
                            index[skill_id] = icon
        
        except FileNotFoundError:
            print(f"Arquivo {dat_file} não encontrado")
        
        return index

    def generate_items_lists(self, site_type: str) -> Dict[str, int]:
        """Gera listas de items por action type"""
        dat_file = f"databases/items_{site_type}.dat"
        
        # 3 listas separadas
        items_skill_success = []
        items_skill_reduce = []
        items_peel = []
        
        try:
            with open(dat_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            items = content.split('item_name_begin')
            
            action_map = {
                'action_peel': 'PEEL',
                'action_skill_reduce': 'SKILL_REDUCE',
                'action_skill_reduce_on_skill_success': 'SKILL_REDUCE_ON_SKILL_SUCCESS'
            }
            
            for item_block in items[1:]:
                id_match = re.search(r'id=(\d+)', item_block)
                if not id_match:
                    continue
                
                item_id = id_match.group(1)
                
                # Buscar default_action
                action_match = re.search(r'default_action=\[([^\]]+)\]', item_block)
                
                if not action_match:
                    continue
                
                action = action_match.group(1).strip()
                
                # Separar nas 3 categorias
                if action == 'action_skill_reduce_on_skill_success':
                    items_skill_success.append({
                        'id': item_id,
                        'default_action': action_map[action]
                    })
                elif action == 'action_skill_reduce':
                    items_skill_reduce.append({
                        'id': item_id,
                        'default_action': action_map[action]
                    })
                elif action == 'action_peel':
                    items_peel.append({
                        'id': item_id,
                        'default_action': action_map[action]
                    })
            
            # Salvar os 3 JSONs na raiz
            file_prefix = f"items_{site_type}_"
            
            with open(f"{file_prefix}action_skill_reduce_on_skill_success.json", 'w', encoding='utf-8') as f:
                json.dump(items_skill_success, f, indent=2, ensure_ascii=False)
            
            with open(f"{file_prefix}action_skill_reduce.json", 'w', encoding='utf-8') as f:
                json.dump(items_skill_reduce, f, indent=2, ensure_ascii=False)
            
            with open(f"{file_prefix}action_peel.json", 'w', encoding='utf-8') as f:
                json.dump(items_peel, f, indent=2, ensure_ascii=False)
            
            # Atualizar extractable_count no config
            total_extractable = len(items_skill_success) + len(items_skill_reduce) + len(items_peel)
            
            with self.config._file_lock():
                self.config.data[site_type]["extractable_count"] = total_extractable
                with open(self.config_file, 'w') as f:
                    json.dump(self.config.data, f, indent=2)
            
            return {
                'skill_reduce_on_skill_success': len(items_skill_success),
                'skill_reduce': len(items_skill_reduce),
                'peel': len(items_peel)
            }
            
        except FileNotFoundError:
            raise FileNotFoundError(f"DAT file not found: {dat_file}")
        except Exception as e:
            raise Exception(f"Error generating items lists: {e}")   
