from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path
from core.database import DatabaseManager
from config.config_manager import ConfigManager

@dataclass
class ProblemModel:
    """
    Representa um item com problemas/pendências.
    Substitui o antigo dicionário 'current_problem'.
    """
    config = ConfigManager()
    database = DatabaseManager(config)

    item_id: str
    skill_id: int
    site_type: str  # 'essence' ou 'main'

    issues: List[str] = field(default_factory=list)
    
    # Dados brutos do Scraper (data.json)
    scraper_data: Optional[Dict[str, Any]] = None
    
    # Dados do XML atual (se existir)
    # xml_data geralmente tem chaves: 'file', 'content', 'tree', etc.
    xml_data: Optional[Dict[str, Any]] = None

    needs_fix: bool = True  # ← NOVO
    validation_status: str = 'INVALID'  # ← NOVO
    
    # Helpers para facilitar a vida e limpar o código
    @property
    def has_scraper_data(self) -> bool:
        return self.scraper_data is not None

    @property
    def has_xml(self) -> bool:
        return self.xml_data is not None
    
    @property
    def item_type(self) -> str:
        if self.scraper_data:
            return self.scraper_data.get('scraping_info', {}).get('item_type', '')
        return ''

    @property
    def has_skills(self) -> bool:
        if self.scraper_data:
            return self.scraper_data.get('scraping_info', {}).get('has_skills', False)
        return False
        
    @property
    def box_data(self) -> dict:
        if self.scraper_data:
            return self.scraper_data.get('box_data', {})
        return {}

    def get_skill_id(self) -> Optional[str]:
        if self.scraper_data:
            skill_data = self.scraper_data.get('skill_data', {})
            if skill_data:
                return str(skill_data.get('skill_id')) if skill_data.get('skill_id') else None
        return None
    
    def get_skill_level(self) -> Optional[int]:
        if self.scraper_data:
            skill_data = self.scraper_data.get('skill_data', {})
            if skill_data:
                return int(skill_data.get('skill_level')) if skill_data.get('skill_level') else None
        return None
    
    def get_skill_name(self) -> Optional[str]:
        if self.scraper_data:
            skill_data = self.scraper_data.get('skill_data', {})
            if skill_data:
                return skill_data.get('skill_name') if skill_data.get('skill_name') else None
        return None
    
    @classmethod
    def get_skill_icon(cls, skill_id: int, site_type: str, scraper_data: dict = None) -> Optional[str]:
        if scraper_data:
            skill_data = scraper_data.get('skill_data', {})
            if skill_data and skill_data.get('skill_icon'):
                return skill_data.get('skill_icon')
        
        # Busca no índice de ícones (skillgrp.dat)
        if site_type == 'essence':
            icon = cls.database.SKILLGRP_INDEX_ESSENCE.get(int(skill_id))
        else: 
            icon = cls.database.SKILLGRP_INDEX.get(int(skill_id))
        return icon if icon else None
    
    def get_item_id(self) -> Optional[str]:
        if self.scraper_data:
            return self.scraper_data.get('item_id')
        else: self.database.ITEM_INDEX.get(int(self.item_id))            