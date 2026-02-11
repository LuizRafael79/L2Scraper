# Arquivo: core/types.py
from typing import TypedDict, List, Optional, Any

class ItemData(TypedDict):
    id: str
    name: str
    additionalname: str
    default_action: str

class SkillData(TypedDict):
    skill_id: int
    skill_level: int
    name: str

# Aproveitando para definir o que usamos nos Handlers:
class ScrapingInfo(TypedDict, total=False):
    item_type: str
    has_skills: bool
    is_extractable: bool
    site_type: str

class ScraperData(TypedDict, total=False):
    scraping_info: ScrapingInfo
    box_data: Dict[str, List[Any]]
    skill_data: Dict[str, Any]