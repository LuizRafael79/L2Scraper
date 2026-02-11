import json
from pathlib import Path
from typing import Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from config.config_manager import ConfigManager

class ScraperHandler:
    def __init__(self, config: "ConfigManager" = None): # type: ignore
        """
        Inicializa o ScraperHandler.
        :param config: Instância do ConfigManager para acesso ao root_path
        """
        self.config = config

    def normalize_count(self, count_value) -> str:
        """
        Normaliza valores de count: remove espaços e converte para string limpa
        Ex: "1 000" -> "1000", "10 000" -> "10000"
        """
        if count_value is None:
            return "1"
        
        if isinstance(count_value, (int, float)):
            return str(int(count_value))
        
        if isinstance(count_value, str):
            # Remove TODOS os espaços e separadores comuns
            cleaned = count_value.replace(' ', '').replace(',', '').replace('.', '')
            
            if not cleaned:
                return "1"
            
            return cleaned
        
        return str(count_value)

    def normalize_scraper_counts(self, scraper_data: Dict) -> Dict:
        """Normaliza apenas os counts no scraper data"""
        if not scraper_data or 'box_data' not in scraper_data:
            return scraper_data
        
        box_data = scraper_data['box_data']
        
        def normalize_item_counts(item):
            if 'count' in item:
                item['count'] = self.normalize_count(item['count'])
            if 'min' in item:
                item['min'] = self.normalize_count(item['min'])
            if 'max' in item:
                item['max'] = self.normalize_count(item['max'])
            return item
        
        # Normalizar listas se existirem
        for key in ['guaranteed_items', 'random_items', 'possible_items']:
            if key in box_data and isinstance(box_data[key], list):
                box_data[key] = [normalize_item_counts(item) for item in box_data[key]]
        
        return scraper_data

    def load_scraper_data(self, item_id: str, site_type: str) -> Optional[Dict]:
        """Carrega e normaliza o data.json do item"""
        try:
            # Tenta usar o root_path do config, senão tenta descobrir (fallback)
            if self.config:
                base_path = self.config.root_path
            else:
                # Fallback: assume que está rodando da raiz ou que html_items está no CWD
                base_path = Path(".")

            data_file = base_path / f"html_items_{site_type}" / str(item_id) / "data.json"
            
            if data_file.exists():
                with open(data_file, 'r', encoding='utf-8') as f:
                    scraper_data = json.load(f)                

                return self.normalize_scraper_counts(scraper_data)
                
        except Exception as e:
            print(f"Erro ao carregar dados do Scraper para {item_id}: {e}")
            
        return None

    def get_skill_id(self, scraper_data: dict) -> Optional[str]:
        """Extrai skill_id dos dados do scraper"""
        if not scraper_data or not isinstance(scraper_data, dict):
            return ""
        
        skill_data = scraper_data.get('skill_data', {})
        if skill_data:
            skill_id = skill_data.get('skill_id')
            if skill_id is not None:
                return str(skill_id)
                
        return ""
    
    def get_skill_level(self, scraper_data: dict) -> Optional[int]:
        """Extrai skill_level dos dados do scraper"""
        if not scraper_data or not isinstance(scraper_data, dict):
            return None
        
        skill_data = scraper_data.get('skill_data', {})
        if skill_data:
            skill_level = skill_data.get('skill_level')
            if skill_level is not None:
                return int(skill_level)
        
        return None