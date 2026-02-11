import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Set
from collections import defaultdict
import json

class SkillTreeDuplicationDetector:
    """Detecta e relata skills duplicadas em múltiplos arquivos"""
    
    def __init__(self, skilltree_path: str, site_type: str = "main"):
        self.skilltree_path = Path(skilltree_path)
        self.site_type = site_type
        self.site_folder = self.skilltree_path / site_type.capitalize()
        
        # skill_id -> {filename -> [skill objects]}
        self.skills_by_file: Dict[str, Dict[str, List[Dict]]] = defaultdict(lambda: defaultdict(list))
        
        # skill_id -> list of files
        self.skill_files: Dict[str, List[str]] = defaultdict(list)
        
        # Estatísticas
        self.total_files = 0
        self.total_unique_skills = 0
        self.duplicated_skills = {}  # skill_id -> count of files
        
        self.scan_root_xml_files()
    
    def scan_root_xml_files(self):
        """Varre apenas XMLs na RAIZ de {site} (não em subpastas)"""
        if not self.site_folder.exists():
            raise FileNotFoundError(f"Skilltree folder not found: {self.site_folder}")
        
        # Pegar apenas arquivos XML na raiz (não recursivamente)
        xml_files = list(self.site_folder.glob('*.xml'))
        
        if not xml_files:
            print(f"⚠️ No XML files found in root of: {self.site_folder}")
            return
        
        print(f"📁 Found {len(xml_files)} XML files in {self.site_folder} (root only)")
        
        for xml_file in sorted(xml_files):
            self._parse_xml_file(xml_file)
        
        # Identificar skills duplicadas
        for skill_id, files in self.skill_files.items():
            if len(files) > 1:
                self.duplicated_skills[skill_id] = len(files)
        
        self.total_files = len(xml_files)
        self.total_unique_skills = len(self.skill_files)
        
        print(f"\n✅ Scanned {self.total_files} files")
        print(f"📊 Total unique skills: {self.total_unique_skills}")
        print(f"🔗 Duplicated skills: {len(self.duplicated_skills)}")
    
    def _parse_xml_file(self, xml_file: Path):
        """Extrai skills de um arquivo XML"""
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            filename = xml_file.name
            
            # Procurar por todas as skills
            for skill_elem in root.findall('.//skill'):
                skill_id = skill_elem.get('skillId')
                skill_name = skill_elem.get('skillName', 'Unknown')
                skill_level = skill_elem.get('skillLevel', '1')
                
                if skill_id:
                    skill_key = f"{skill_id}_{skill_level}"
                    
                    # Armazenar informações da skill
                    skill_info = {
                        'skill_id': skill_id,
                        'skill_name': skill_name,
                        'skill_level': skill_level,
                        'filename': filename
                    }
                    
                    self.skills_by_file[skill_key][filename].append(skill_info)
                    
                    if filename not in self.skill_files[skill_key]:
                        self.skill_files[skill_key].append(filename)
        
        except Exception as e:
            print(f"⚠️ Error parsing {xml_file.name}: {e}")
    
    def get_duplicated_skills(self) -> Dict[str, List[str]]:
        """Retorna skills duplicadas com lista de arquivos"""
        result = {}
        for skill_key, files in self.skill_files.items():
            if len(files) > 1:
                result[skill_key] = sorted(files)
        return result
    
    def print_detailed_report(self, output_file: str = None):
        """Gera relatório detalhado de duplicações"""
        report_lines = []
        
        report_lines.append("=" * 80)
        report_lines.append(f"🔍 SKILLTREE DUPLICATION REPORT - {self.site_type.upper()}")
        report_lines.append("=" * 80)
        report_lines.append("")
        
        # Resumo
        report_lines.append("📊 SUMMARY")
        report_lines.append(f"  Total files scanned: {self.total_files}")
        report_lines.append(f"  Total unique skills: {self.total_unique_skills}")
        report_lines.append(f"  Duplicated skills: {len(self.duplicated_skills)}")
        report_lines.append("")
        
        # Listar arquivos
        report_lines.append("📁 FILES SCANNED")
        for filename in sorted(set(f for files in self.skill_files.values() for f in files)):
            count = sum(1 for files in self.skill_files.values() if filename in files)
            report_lines.append(f"  {filename:<40} ({count} skills)")
        report_lines.append("")
        
        # Detalhar cada skill duplicada
        report_lines.append("🔗 DUPLICATED SKILLS DETAILS")
        report_lines.append("-" * 80)
        
        duplicated_sorted = sorted(
            self.skill_files.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )
        
        for skill_key, files in duplicated_sorted:
            if len(files) > 1:
                skill_id, skill_level = skill_key.rsplit('_', 1)
                
                # Pegar info da skill
                skill_names = set()
                for filename in files:
                    for skill_info in self.skills_by_file[skill_key][filename]:
                        skill_names.add(skill_info['skill_name'])
                
                skill_name = list(skill_names)[0] if skill_names else "Unknown"
                
                report_lines.append(f"\n  ID: {skill_id} | Level: {skill_level} | Name: {skill_name}")
                report_lines.append(f"  Found in {len(files)} files:")
                
                for filename in sorted(files):
                    report_lines.append(f"    ✓ {filename}")
        
        report_lines.append("\n" + "=" * 80)
        report_lines.append(f"Report generated for: {self.site_type}")
        report_lines.append("=" * 80)
        
        # Imprimir no console
        report_text = '\n'.join(report_lines)
        print("\n" + report_text)
        
        # Salvar em arquivo se solicitado
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report_text)
            print(f"\n💾 Report saved to: {output_file}")
        
        return report_text
    
    def export_json(self, output_file: str) -> Dict:
        """Exporta dados em JSON"""
        data = {
            'site_type': self.site_type,
            'summary': {
                'total_files': self.total_files,
                'total_unique_skills': self.total_unique_skills,
                'duplicated_skills_count': len(self.duplicated_skills)
            },
            'duplicated_skills': {}
        }
        
        for skill_key, files in self.skill_files.items():
            if len(files) > 1:
                skill_id, skill_level = skill_key.rsplit('_', 1)
                
                skill_names = set()
                for filename in files:
                    for skill_info in self.skills_by_file[skill_key][filename]:
                        skill_names.add(skill_info['skill_name'])
                
                data['duplicated_skills'][skill_key] = {
                    'skill_id': skill_id,
                    'skill_level': skill_level,
                    'skill_name': list(skill_names)[0] if skill_names else "Unknown",
                    'files': sorted(files),
                    'file_count': len(files)
                }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"💾 JSON exported to: {output_file}")
        return data
    
    def get_skill_locations(self, skill_id: str) -> Dict[str, List[str]]:
        """Retorna em quais arquivos uma skill específica aparece"""
        result = {}
        for skill_key, files in self.skill_files.items():
            if skill_key.startswith(f"{skill_id}_"):
                result[skill_key] = sorted(files)
        return result