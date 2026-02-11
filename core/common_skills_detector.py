import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Set, Dict
from collections import Counter

class CommonSkillsDetector:
    """Detecta skills que são comuns a múltiplas classes"""
    
    def __init__(self, skilltree_path: str, site_type: str = "main"):
        self.skilltree_path = Path(skilltree_path)
        self.site_type = site_type
        self.site_folder = self.skilltree_path / site_type
        self.skill_occurrences: Dict[str, int] = {}  # skill_id -> count
        self.skill_classes: Dict[str, Set[str]] = {}  # skill_id -> set of classes
        self.all_skills: Set[str] = set()  # todos os skillIds encontrados
        self.common_skills: Set[str] = set()  # skills que aparecem em múltiplas classes
        self.scan_xml_files()
    
    def scan_xml_files(self):
        """Varre todas as XMLs na pasta {site} recursivamente"""
        if not self.site_folder.exists():
            raise FileNotFoundError(f"Skilltree folder not found: {self.site_folder}")
        
        xml_files = list(self.site_folder.rglob('*.xml'))
        
        if not xml_files:
            raise FileNotFoundError(f"No XML files found in: {self.site_folder}")
        
        print(f"📁 Found {len(xml_files)} XML files in {self.site_folder}")
        
        for xml_file in xml_files:
            self._parse_xml_file(xml_file)
        
        # Identificar skills comuns (que aparecem em mais de uma classe/arquivo)
        for skill_id, count in self.skill_occurrences.items():
            if count > 1:
                self.common_skills.add(skill_id)
        
        print(f"✅ Scanned {len(xml_files)} files")
        print(f"📊 Total unique skills: {len(self.all_skills)}")
        print(f"🔗 Common skills (appear multiple times): {len(self.common_skills)}")
    
    def _parse_xml_file(self, xml_file: Path):
        """Extrai skillIds de um arquivo XML"""
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # Procurar por todas as skills
            for skill_elem in root.findall('.//skill'):
                skill_id = skill_elem.get('skillId')
                
                if skill_id:
                    self.all_skills.add(skill_id)
                    
                    # Contar ocorrências
                    if skill_id not in self.skill_occurrences:
                        self.skill_occurrences[skill_id] = 0
                    self.skill_occurrences[skill_id] += 1
                    
                    # Rastrear qual classe tem essa skill
                    class_name = xml_file.parent.name
                    if skill_id not in self.skill_classes:
                        self.skill_classes[skill_id] = set()
                    self.skill_classes[skill_id].add(class_name)
        
        except Exception as e:
            print(f"⚠️ Error parsing {xml_file}: {e}")
    
    def is_common_skill(self, skill_id: str) -> bool:
        """Verifica se uma skill é comum (aparece em múltiplas classes)"""
        return skill_id in self.common_skills
    
    def get_common_skills(self) -> Set[str]:
        """Retorna set de todos os skillIds comuns"""
        return self.common_skills
    
    def get_skill_info(self, skill_id: str) -> Dict:
        """Retorna informações sobre uma skill"""
        return {
            'skill_id': skill_id,
            'occurrences': self.skill_occurrences.get(skill_id, 0),
            'classes': list(self.skill_classes.get(skill_id, [])),
            'is_common': self.is_common_skill(skill_id)
        }
    
    def print_common_skills_report(self):
        """Imprime relatório de skills comuns"""
        print(f"\n{'='*60}")
        print(f"📋 COMMON SKILLS REPORT ({self.site_type.upper()})")
        print(f"{'='*60}\n")
        
        # Ordenar por frequência
        sorted_skills = sorted(
            self.common_skills,
            key=lambda x: self.skill_occurrences[x],
            reverse=True
        )
        
        for skill_id in sorted_skills[:20]:  # Top 20
            info = self.get_skill_info(skill_id)
            classes = ', '.join(sorted(info['classes']))
            print(f"ID: {skill_id} | Appears: {info['occurrences']}x | Classes: {classes}")
        
        if len(sorted_skills) > 20:
            print(f"\n... and {len(sorted_skills) - 20} more common skills")
        
        print(f"\n{'='*60}")