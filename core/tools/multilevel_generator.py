import json
import glob
import os
import sys

# Hack para garantir que o script encontre o módulo 'core' e 'config'
# Adiciona o diretório raiz do projeto ao PATH do Python
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.config_manager import ConfigManager
from core.database import DatabaseManager

class MultilevelGrouper:
    def __init__(self, items_directory, site_type='main'):
        """
        items_directory: Pasta dos JSONs (ex: 'html_items_main')
        site_type: 'main' ou 'essence' (para escolher o DAT correto)
        """
        self.items_directory = items_directory
        self.site_type = site_type
        self.grouped_data = {}

        # 1. INICIALIZA O DATABASE (Carrega os DATs na memória)
        print("📥 Carregando DATs via DatabaseManager...")
        self.config = ConfigManager()
        self.database = DatabaseManager(self.config) 
        # O __init__ do DatabaseManager já chama _ensure_indexes_loaded
        print("✅ DATs carregados.")

    def _get_db_item_name(self, item_id):
        """Busca nome formatado (Name - Additional) usando ItemString"""
        try:
            iid = int(item_id)
            
            # Pega o objeto do Database
            if self.site_type == 'essence':
                raw = DatabaseManager.ITEM_INDEX_ESSENCE.get(iid)
            else:
                raw = DatabaseManager.ITEM_INDEX.get(iid)
            
            if raw and isinstance(raw, MultilevelGrouper):
                # 1. Verifica se é nossa 'ItemString' especial (que tem as partes separadas)
                if hasattr(raw, 'pure_name') and hasattr(raw, 'add_name'):
                    # SE tiver adicional, retorna "Nome - Adicional"
                    if raw.add_name:
                        return f"{raw.pure_name} - {raw.add_name}"
                    # Senão, retorna só o nome puro
                    return raw.pure_name
                
                # 2. Fallback: Se for string comum antiga, retorna ela mesma
                return str(raw)
                
            return f"Unknown Item {item_id}"
        except:
            return f"Unknown Item {item_id}"

    def _get_db_skill_name(self, skill_id):
        """Busca nome da skill no DAT correto"""
        try:
            sid = int(skill_id)
            if self.site_type == 'essence':
                raw = DatabaseManager.SKILL_INDEX_ESSENCE.get(sid)
            else:
                raw = DatabaseManager.SKILL_INDEX.get(sid)
            
            if raw:
                # Skills no DB as vezes retornam lista de nomes por level
                # Pegamos o primeiro (level 1) como nome genérico
                if isinstance(raw, list) and len(raw) > 0:
                    return str(raw[0])
                return str(raw)
            return f"Unknown Skill {skill_id}"
        except:
            return f"Unknown Skill {skill_id}"

    def run(self):
        print(f"🔄 Iniciando agrupamento em: {self.items_directory}...")
        
        search_path = os.path.join(self.items_directory, "*", "data.json")
        files = glob.glob(search_path)
        
        count = 0
        for file_path in files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self._process_item(data)
                count += 1
            except Exception as e:
                print(f"❌ Erro ao ler {file_path}: {e}")

        self._sort_and_finalize()
        
        output_filename = f"multilevel_skills_{self.site_type}.json"
        self._save_to_file(output_filename)
        
        print(f"✅ Concluído! Arquivo gerado: {output_filename}")
        print(f"📊 Processados {count} arquivos. Skills agrupadas: {len(self.grouped_data)}")

    def _process_item(self, data):
        skill_info = data.get('skill_data')
        if not skill_info:
            return

        skill_id = str(skill_info.get('skill_id'))
        if not skill_id or skill_id == "None":
            return

        skill_level = int(skill_info.get('skill_level', 1))
        item_id = str(data.get('item_id'))

        # --- A MÁGICA: Buscar nomes no DB, não no JSON ---
        skill_name_db = self._get_db_skill_name(skill_id)
        item_name_db = self._get_db_item_name(item_id)

        # Inicializa a skill no dicionário mestre
        if skill_id not in self.grouped_data:
            self.grouped_data[skill_id] = {
                "skill_name": skill_name_db, # Nome oficial do DAT
                "levels": []
            }

        # Pega o box data do scraper
        box_data = data.get('box_data', {
            "guaranteed_items": [], "random_items": [], "possible_items": []
        })
        
        # IMPORTANTE: Os itens DENTRO do box_data (extractables) 
        # já devem ter vindo com nomes corretos do parser do scraper?
        # Se você quiser sanitizar ELES também, teria que iterar o box_data aqui.
        # Mas geralmente o item pai é o crítico.

        level_entry = {
            "level": skill_level,
            "item_id": item_id,
            "item_name": item_name_db, # Nome oficial do DAT
            "box_data": box_data
        }

        self.grouped_data[skill_id]["levels"].append(level_entry)

    def _sort_and_finalize(self):
        to_remove = []
        for skill_id, content in self.grouped_data.items():
            content["levels"].sort(key=lambda x: x['level'])
            
            if len(content["levels"]) < 2:
                to_remove.append(skill_id)
                continue

            if content["levels"]:
                content["max_level"] = content["levels"][-1]['level']
            else:
                content["max_level"] = 1

        for k in to_remove:
            del self.grouped_data[k]

    def _save_to_file(self, filename):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.grouped_data, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    # Exemplo de uso:
    # Ajuste para rodar Main ou Essence
    
    # MAIN
    grouper_main = MultilevelGrouper("html_items_main", site_type='main') 
    grouper_main.run()
    
    # ESSENCE (Descomente se precisar)
    # grouper_essence = MultilevelGrouper("html_items_essence", site_type='essence') 
    # grouper_essence.run()