# scraping_stats.py
class ScrapingStats:
    def __init__(self):
        # Estatísticas de Progresso
        self.total_items = 0
        self.processed_items = 0
        self.successful_items = 0
        self.failed_items = 0
        self.not_found_items = 0
        
        # Estatísticas de Classificação
        self.item_box_found = 0
        self.skill_box_found = 0
        
        # Estatísticas de Conteúdo
        self.total_guaranteed_items = 0
        self.total_random_items = 0
        self.total_possible_items = 0
        
        # Estatísticas por Tipo
        self.item_guaranteed = 0
        self.item_random = 0
        self.item_possible = 0
        self.skill_guaranteed = 0
        self.skill_random = 0
        self.skill_possible = 0
        
    def update_from_dict(self, stats_dict):
        for key, value in stats_dict.items():
            if hasattr(self, key):
                setattr(self, key, value)