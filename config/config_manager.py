import json
import fcntl
from pathlib import Path
from typing import Dict, List
from contextlib import contextmanager

class ConfigManager:
    def __init__(self):
        # Define a raiz do projeto baseada na localização deste arquivo (config/config_manager.py)
        # .parent = pasta config
        # .parent.parent = raiz do projeto
        self.root_path = Path(__file__).resolve().parent.parent
        
        self.config_file = self.root_path / "scraper_config.json"
        self.lock_file = self.root_path / "scraper_config.json.lock"
        self.extractable_types: dict[str, str] = {} 
        self.load_config()
    
    def _file_lock(self):
        """Context manager para file lock (Linux/Unix)"""
        @contextmanager
        def lock():
            # Cria o arquivo de lock se não existir
            if not self.lock_file.exists():
                self.lock_file.touch()
                
            lock_handle = open(self.lock_file, 'w')
            try:
                # Bloqueio exclusivo
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
                yield
            finally:
                # Libera o bloqueio
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
                lock_handle.close()
        
        return lock()
        
    def load_config(self):
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
            except json.JSONDecodeError:
                # Se o arquivo estiver corrompido, recria
                print("⚠️ Config file corrupted. Recreating defaults.")
                self.data = {}
            
            self.migrate_config()
        else:
            # Cria a estrutura padrão inicial
            self.data = {}
            self.migrate_config()
    
    def migrate_config(self):
        """Garante que todas as chaves necessárias existam no config"""
        # Estrutura padrão completa
        default_structure = {
            "processed_items": [],
            "failed_items": [],
            "not_found_items": [],
            "last_item": None,
            "extractable_types": {},
            "total_items": 0,
            "extractable_count": 0,
            "stats": {
                "total_items": 0,
                "processed_items": 0,
                "successful_items": 0,
                "failed_items": 0,
                "not_found_items": 0,
                "item_box_found": 0,
                "skill_box_found": 0,
                "total_guaranteed_items": 0,
                "total_random_items": 0,
                "total_possible_items": 0
            }
        }

        changed = False
        for site_type in ["essence", "main"]:
            if site_type not in self.data:
                self.data[site_type] = {}
                changed = True
            
            site_data = self.data[site_type]
            
            # Verifica chaves faltantes recursivamente (nível 1)
            for key, default_value in default_structure.items():
                if key not in site_data:
                    if isinstance(default_value, dict):
                        site_data[key] = default_value.copy()
                    elif isinstance(default_value, list):
                        site_data[key] = default_value.copy()
                    else:
                        site_data[key] = default_value
                    changed = True
                
                # Verifica sub-chaves do stats
                if key == "stats" and isinstance(site_data[key], dict):
                    for stat_k, stat_v in default_structure["stats"].items():
                        if stat_k not in site_data[key]:
                            site_data[key][stat_k] = stat_v
                            changed = True

        if changed:
            self.save_config()
    
    def save_config(self):
        """🔒 SALVA COM FILE LOCK"""
        with self._file_lock():
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2)

    def save_stats(self, site_type: str, stats: Dict):
        """Salva estatísticas no config"""
        with self._file_lock():
            self.data[site_type]["stats"] = stats
            # Otimização: Não precisamos salvar o arquivo inteiro a cada update de stat se for frequente,
            # mas para segurança, manteremos o dump.
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2)
    
    def load_stats(self, site_type: str) -> Dict:
        """Carrega estatísticas da memória"""
        return self.data[site_type]["stats"].copy()
    
    def update_stats_from_files(self, site_type: str) -> Dict:
        """
        Lê o disco para contar arquivos processados real.
        Útil para quando reinicia a aplicação.
        """
        # ⚠️ CORREÇÃO CRÍTICA: Usar self.root_path
        output_dir = self.root_path / f"html_items_{site_type}"
        
        if not output_dir.exists():
            return self.data[site_type]["stats"]
            
        stats = {
            "total_items": self.data[site_type].get("extractable_count", 0),
            "processed_items": 0,
            "successful_items": 0,
            "failed_items": 0,
            "not_found_items": 0,
            "item_box_found": 0,
            "skill_box_found": 0,
            "total_guaranteed_items": 0,
            "total_random_items": 0,
            "total_possible_items": 0
        }
        
        # Lista diretórios numéricos apenas
        processed_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.isdigit()]
        stats["processed_items"] = len(processed_dirs)
        
        for item_dir in processed_dirs:
            json_file = item_dir / "data.json"
            if json_file.exists():
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    if data.get('scraping_info', {}).get('is_extractable', False):
                        stats["successful_items"] += 1
                        
                        box_data = data.get('box_data', {})
                        item_type = data.get('scraping_info', {}).get('item_type', '')
                        
                        if item_type == "PEEL":
                            stats["item_box_found"] += 1
                        else:
                            stats["skill_box_found"] += 1
                            
                        stats["total_guaranteed_items"] += len(box_data.get("guaranteed_items", []))
                        stats["total_random_items"] += len(box_data.get("random_items", []))
                        stats["total_possible_items"] += len(box_data.get("possible_items", []))
                    else:
                        stats["not_found_items"] += 1
                        
                except Exception:
                    # Se arquivo corrompido, conta como falha
                    stats["failed_items"] += 1
        
        # Sincroniza com as listas de falha conhecidas no config
        stats["failed_items"] = len(self.data[site_type]["failed_items"])
        stats["not_found_items"] = len(self.data[site_type]["not_found_items"])
        
        # Atualiza a memória e salva
        self.save_stats(site_type, stats)
        return stats
            
    def add_processed_item(self, site_type: str, item_id: str):
        with self._file_lock():
            changed = False
            if item_id not in self.data[site_type]["processed_items"]:
                self.data[site_type]["processed_items"].append(item_id)
                changed = True
            
            if item_id in self.data[site_type]["failed_items"]:
                self.data[site_type]["failed_items"].remove(item_id)
                changed = True
                
            if item_id in self.data[site_type]["not_found_items"]:
                self.data[site_type]["not_found_items"].remove(item_id)
                changed = True
                
            self.data[site_type]["last_item"] = item_id
            
            if changed:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(self.data, f, indent=2)
            
    def add_failed_item(self, site_type: str, item_id: str):
        with self._file_lock():
            changed = False
            if item_id not in self.data[site_type]["failed_items"]:
                self.data[site_type]["failed_items"].append(item_id)
                changed = True
                
            if item_id in self.data[site_type]["processed_items"]:
                self.data[site_type]["processed_items"].remove(item_id)
                changed = True
                
            if item_id in self.data[site_type]["not_found_items"]:
                self.data[site_type]["not_found_items"].remove(item_id)
                changed = True
            
            if changed:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(self.data, f, indent=2)
            
    def add_not_found_item(self, site_type: str, item_id: str):
        with self._file_lock():
            changed = False
            if item_id not in self.data[site_type]["not_found_items"]:
                self.data[site_type]["not_found_items"].append(item_id)
                changed = True
                
            if item_id in self.data[site_type]["processed_items"]:
                self.data[site_type]["processed_items"].remove(item_id)
                changed = True
                
            if item_id in self.data[site_type]["failed_items"]:
                self.data[site_type]["failed_items"].remove(item_id)
                changed = True
                
            if changed:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(self.data, f, indent=2)
            
    def clear_failed_items(self, site_type: str):
        with self._file_lock():
            self.data[site_type]["failed_items"] = []
            with open(self.config_file, 'w') as f:
                json.dump(self.data, f, indent=2)
    
    def get_site_stats(self, site_type: str) -> Dict:
        # Garante que estrutura existe
        if site_type not in self.data:
            self.migrate_config()
            
        return {
            "total_in_dat": self.data[site_type].get("total_items", 0),
            "extractable_count": self.data[site_type].get("extractable_count", 0),
            "processed": len(self.data[site_type]["processed_items"]),
            "failed": len(self.data[site_type]["failed_items"]),
            "not_found": len(self.data[site_type]["not_found_items"])
        }

    def save_current_state(self, site_type: str, stats: dict):
        with self._file_lock():
            self.data[site_type]["last_stats"] = stats
            with open(self.config_file, 'w') as f:
                json.dump(self.data, f, indent=2)

    def load_current_state(self, site_type: str) -> dict:
        return self.data[site_type].get("last_stats", {})
    
    def get_items_to_process(self, site_type: str, full_scan: bool = False) -> List[dict]:  
        """
        Carrega items dos 3 JSONs de prioridade.
        """
        # ⚠️ CORREÇÃO DE PATH: Usa self.root_path
        file_prefix = self.root_path / f"items_{site_type}_"
        
        json_files = [
            f"{file_prefix}action_skill_reduce_on_skill_success.json",
            f"{file_prefix}action_skill_reduce.json",
            f"{file_prefix}action_peel.json"
        ]
        
        # Verificar se existem
        for json_file in json_files:
            if not Path(json_file).exists():
                print(f"⚠️ Lista não encontrada: {json_file}")
                # Não dá raise error para não travar a UI, retorna vazio ou continua
                continue
        
        all_items = []
        
        # Carregar as listas
        for json_file in json_files:
            p = Path(json_file)
            if p.exists():
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        items = json.load(f)
                        all_items.extend(items)
                except Exception as e:
                    print(f"Erro ao ler {p.name}: {e}")
        
        if not all_items:
            return []
        
        if full_scan:
            print(f"🔄 Full scan: {len(all_items)} itens.")
            return all_items
        
        # 📊 MODO INCREMENTAL
        processed_set = set(self.data[site_type]["processed_items"])
        not_found_set = set(self.data[site_type]["not_found_items"])
        failed_set = set(self.data[site_type]["failed_items"])
        
        # Remove items já processados ou não encontrados
        already_checked = processed_set | not_found_set
        
        candidates = [
            item for item in all_items 
            if str(item['id']) not in already_checked
        ]
        
        # Priorizar falhos (Retry)
        failed_candidates = [item for item in all_items if str(item['id']) in failed_set]
        # Remover duplicatas dos falhos na lista de novos
        other_candidates = [item for item in candidates if str(item['id']) not in failed_set]
        
        final_list = failed_candidates + other_candidates
        
        print(f"📊 Incremental: {len(final_list)} para processar ({len(failed_candidates)} retries)")
        
        return final_list