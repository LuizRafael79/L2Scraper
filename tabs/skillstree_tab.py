from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                           QPushButton, QLabel, QProgressBar, QTextEdit,
                           QGroupBox, QGridLayout, QComboBox, QFrame)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QTextCursor

import time

class SkillTreeTab(QWidget):
    stats_updated = pyqtSignal()
    worker_created = pyqtSignal(object, str)
    
    def __init__(self, config, database):
        super().__init__()
        self.config = config
        self.database = database
        self.scraper_worker = None
        self.site_type = "main"

        # Class Mapping "Essence" - Human Readable -> Slug -> Folder -> XML
        self.class_mapping_essence = {
            # --- Human Fighter ---
            "Human Fighter": {"slug": "fighter", "folder": "StartingClass", "xml": "HumanFighter"},
            "Warrior": {"slug": "warrior", "folder": "1stClass", "xml": "Warrior"},
            "Warlord": {"slug": "warlord", "folder": "2ndClass", "xml": "Warlord"},
            "Dreadnought": {"slug": "dreadnought", "folder": "3rdClass", "xml": "Dreadnought"},
            "Gladiator": {"slug": "gladiator", "folder": "2ndClass", "xml": "Gladiator"},
            "Duelist": {"slug": "duelist", "folder": "3rdClass", "xml": "Duelist"},
            "Knight": {"slug": "knight", "folder": "1ndClass", "xml": "Knight"},
            "Paladin": {"slug": "paladin", "folder": "2ndClass", "xml": "Paladin"},
            "Phoenix Knight": {"slug": "phoenix_knight", "folder": "3rdClass", "xml": "PhoenixKnight"},
            "Dark Avenger": {"slug": "dark_avenger", "folder": "2ndClass", "xml": "DarkAvenger"},
            "Hell Knight": {"slug": "hell_knight", "folder": "3rdClass", "xml": "HellKnight"},
            "Rogue": {"slug": "rogue", "folder": "1stClass", "xml": "Rogue"},
            "Hawkeye": {"slug": "hawkeye", "folder": "2ndClass", "xml": "Hawkeye"},
            "Sagittarius": {"slug": "sagittarius", "folder": "3rdClass", "xml": "Sagittarius"},
            "Treasure Hunter": {"slug": "treasure_hunter", "folder": "2ndClass", "xml": "TreasureHunter"},
            "Adventurer": {"slug": "adventurer", "folder": "3rdClass", "xml": "Adventurer"},
            # --- Human Mystic ---
            "Human Mystic": {"slug": "mystic", "folder": "StartingClass", "xml": "HumanMystic"},
            "Wizard": {"slug": "wizard", "folder": "1stClass", "xml": "Wizard"},
            "Sorcerer": {"slug": "sorcerer", "folder": "2ndClass", "xml": "Sorcerer"},
            "Archmage": {"slug": "archmage", "folder": "3rdClass", "xml": "Archmage"},
            "Necromancer": {"slug": "necromancer", "folder": "2ndClass", "xml": "Necromancer"},
            "Soultaker": {"slug": "soultaker", "folder": "3rdClass", "xml": "Soultaker"},
            "Warlock": {"slug": "warlock", "folder": "2ndClass", "xml": "Warlock"},
            "Arcana Lord": {"slug": "arcana_lord", "folder": "3rdClass", "xml": "ArcanaLord"},
            "Cleric": {"slug": "cleric", "folder": "1stClass", "xml": "Cleric"},
            "Bishop": {"slug": "bishop", "folder": "2ndClass", "xml": "Bishop"},
            "Cardinal": {"slug": "cardinal", "folder": "3rdClass", "xml": "Cardinal"},
            "Prophet": {"slug": "prophet", "folder": "2ndClass", "xml": "Prophet"},
            "Hierophant": {"slug": "hierophant", "folder": "3rdClass", "xml": "Hierophant"},
            # --- Human Death Knight ---
            "Death Pilgrim": {"slug": "human_deathknight_0", "folder": "DeathKnight", "xml": "DeathKnightHuman"},
            "Death Blade": {"slug": "human_deathknight_1", "folder": "DeathKnight", "xml": "DeathPilgrimHuman"},
            "Death Messenger": {"slug": "human_deathknight_2", "folder": "DeathKnight", "xml": "DeathMessengerHuman"},
            "Death Knight": {"slug": "human_deathknight_3", "folder": "DeathKnight", "xml": "DeathKnightHuman"},
            # --- Human Assassin Male ---
            "Assassin Male - 1": {"slug": "secret_assassin_male_0", "folder": "Assassin", "xml": "AssassinMale0"},
            "Assassin Male - 2": {"slug": "secret_assassin_male_1", "folder": "Assassin", "xml": "AssassinMale1"},
            "Assassin Male - 3": {"slug": "secret_assassin_male_2", "folder": "Assassin", "xml": "AssassinMale2"},
            "Assassin Male - 4": {"slug": "secret_assassin_male_3", "folder": "Assassin", "xml": "AssassinMale3"},
            # --- Human Warg ---
            "Warg - 1": {"slug": "werewolf_0", "folder": "Warg", "xml": "Warg0"},
            "Warg - 2": {"slug": "werewolf_1", "folder": "Warg", "xml": "Warg1"},
            "Warg - 3": {"slug": "werewolf_2", "folder": "Warg", "xml": "Warg2"},
            "Warg - 4": {"slug": "werewolf_3", "folder": "Warg", "xml": "Warg3"},
            # --- Elf Fighter ---
            "Elven Fighter": {"slug": "elven_fighter", "folder": "StartingClass", "xml": "ElvenFighter"},
            "Elven Knight": {"slug": "elven_knight", "folder": "1stClass", "xml": "ElvenKnight"},
            "Temple Knight": {"slug": "temple_knight", "folder": "2ndClass", "xml": "TempleKnight"},
            "Eva's Templar": {"slug": "evas_templar", "folder": "3rdClass", "xml": "Eva'sTemplar"},
            "Sword Singer": {"slug": "swordsinger", "folder": "2ndClass", "xml": "SwordSinger"},
            "Sword Muse": {"slug": "sword_muse", "folder": "3rdClass", "xml": "SwordMuse"},
            "Elven Scout": {"slug": "elven_scout", "folder": "2ndClass", "xml": "ElvenScout"},
            "Plains Walker": {"slug": "plains_walker", "folder": "3rdClass", "xml": "PlainsWalker"},
            "Wind Rider": {"slug": "wind_rider", "folder": "3rdClass", "xml": "WindRider"},
            "Silver Ranger": {"slug": "silver_ranger", "folder": "2ndClass", "xml": "SilverRanger"},
            "Moonlight Sentinel": {"slug": "moonlight_sentinel", "folder": "3rdClass", "xml": "MoonlightSentinel"},
            # --- Elf Dark Knight ---
            "Death Pilgrim": {"slug": "elf_deathknight_0", "folder": "DeathKnight", "xml": "DeathPilgrimElf"},
            "Death Blade": {"slug": "elf_deathknight_1", "folder": "DeathKnight", "xml": "DeathBladerElf"},
            "Death Messenger": {"slug": "elf_deathknight_2", "folder": "DeathKnight", "xml": "DeathMessengerElf"},
            "Death Knight": {"slug": "elf_deathknight_3", "folder": "DeathKnight", "xml": "DeathKnightElf"},
            # --- Elf Mystic ---
            "Elven Mystic": {"slug": "elven_mage", "folder": "StartingClass", "xml": "ElvenMystic"},
            "Elven Wizard": {"slug": "elven_wizard", "folder": "1stClass", "xml": "ElvenWizard"},
            "Spellsinger": {"slug": "spellsinger", "folder": "2ndClass", "xml": "Spellsinger"},
            "Mystic Muse": {"slug": "mystic_muse", "folder": "3rdClass", "xml": "MysticMuse"},
            "Elven Oracle": {"slug": "oracle", "folder": "1ndClass", "xml": "ElvenOracle"},
            "Elven Elder": {"slug": "elven_elder", "folder": "2rdClass", "xml": "ElvenElder"},
            "Eva's Saint": {"slug": "evas_saint", "folder": "3rdClass", "xml": "Eva'sSaint"},
            # --- Dark Elf Fighter ---
            "Dark Fighter": {"slug": "dark_fighter", "folder": "StartingClass", "xml": "DarkFighter"},
            "Dark Knight": {"slug": "palus_knight", "folder": "1stClass", "xml": "DarkKnight"},
            "Shillien Knight": {"slug": "shillien_knight", "folder": "2ndClass", "xml": "ShillienKnight"},
            "Shlllien Templar": {"slug": "shillien_templar", "folder": "3rdClass", "xml": "ShillienTemplar"},
            "BladeDancer": {"slug": "bladedancer", "folder": "2ndClass", "xml": "BladeDancer"},
            "Spectral Dancer": {"slug": "spectral_dancer", "folder": "3rdClass", "xml": "SpectralDancer"},
            "Dark Slayer": {"slug": "dark_slayer", "folder": "1ndClass", "xml": "DarkSlayer"},
            "Abyss Walker": {"slug": "abyss_walker", "folder": "2ndClass", "xml": "AbyssWalker"},
            "Ghost Ranger": {"slug": "ghost_ranger", "folder": "3rdClass", "xml": "GhostRanger"},
            "Phantom Ranger": {"slug": "phantom_ranger", "folder": "2ndClass", "xml": "PhantomRanger"},
            "Ghost Sentinel": {"slug": "ghost_sentinel", "folder": "3rdClass", "xml": "GhostSentinel"},
            # --- Dark Elf Dark Knight
            "Death Pilgrim": {"slug": "delf_deathknight_0", "folder": "DeathKnight", "xml": "DeathPilgrimDarkElf"},
            "Death Blade": {"slug": "delf_deathknight_1", "folder": "DeathKnight", "xml": "DeathBladeDarkElf"},
            "Death Messenger": {"slug": "delf_deathknight_2", "folder": "DeathKnight", "xml": "DeathMessengerDarkElf"},
            "Death Knight": {"slug": "delf_deathknight_3", "folder": "DeathKnight", "xml": "DeathKnighDarkElf"},
            # --- Dark Elf Mystic ---
            "Dark Mystic": {"slug": "dark_mystic", "folder": "StartingClass", "xml": "DarkWizard"},
            "Dark Wizard": {"slug": "dark_mage", "folder": "1stClass", "xml": "DarkWizard"},
            "SpeelWoller": {"slug": "speelwoller", "folder": "2ndClass", "xml": "Speelwoller"},
            "Storm Screamer": {"slug": "storm_screamer", "folder": "3rdClass", "xml": "StormScreamer"},
            "Shillien Oracle": {"slug": "shillien_oracle", "folder": "1stClass", "xml": "ShillienOracle"},
            "Shillien Elder": {"slug": "shillien_elder", "folder": "2ndClass", "xml": "ShillienElder"},
            "Shillien Saint": {"slug": "shillien_saint", "folder": "3rdClass", "xml": "ShillienSaint"},
            # --- Dark Elf - Assassin ---
            "Assassin Female - 1": {"slug": "secret_assassin_female_0", "folder": "Assassin", "xml": "AssassinFemale0"},
            "Assassin Female - 2": {"slug": "secret_assassin_female_1", "folder": "Assassin", "xml": "AssassinFemale1"},
            "Assassin Female - 3": {"slug": "secret_assassin_female_2", "folder": "Assassin", "xml": "AssassinFemale2"},
            "Assassin Female- 4": {"slug": "secret_assassin_female_3", "folder": "Assassin", "xml": "AssassinFemale3"},
            # --- Dark Elf - Blood Rose ---
            "Blood Rose - 1": {"slug": "rose_vain_0", "folder": "BloodRose", "xml": "BloodRose0"},
            "Blood Rose - 2": {"slug": "rose_vain_1", "folder": "BloodRose", "xml": "BloodRose1"},
            "Blood Rose - 3": {"slug": "rose_vain_2", "folder": "BloodRose", "xml": "BloodRose2"},
            "Blood Rose - 4": {"slug": "rose_vain_3", "folder": "BloodRose", "xml": "BloodRose3"},
            # --- Orc Fighter ---
            "Orc Fighter": {"slug": "orc_fighter", "folder": "StartingClass", "xml": "OrcFighter"},
            "Orc Rider": {"slug": "orc_rider", "folder": "1stClass", "xml": "OrcRider"},
            "Destroyer": {"slug": "destroyer", "folder": "2ndClass", "xml": "Destroyer"},
            "Titan": {"slug": "titan", "folder": "3rdClass", "xml": "Titan"},
            "Orc Monk": {"slug": "orc_monk", "folder": "1stClass", "xml": "OrcMonk"},
            "Tyrant": {"slug": "tyrant", "folder": "2ndClass", "xml": "Tyrant"},
            "Grand Khavatari": {"slug": "grand_khavatari", "folder": "3rdClass", "xml": "GrandKhavatari"},
            # --- Orc Mystic ---
            "Orc Mystic": {"slug": "orc_mystic", "folder": "StartingClass", "xml": "OrcWizard"},
            "Orc Shaman": {"slug": "orc_shaman", "folder": "1stClass", "xml": "OrcShaman"},
            "Overlord": {"slug": "overlord", "folder": "2ndClass", "xml": "Overlord"},
            "Dominator": {"slug": "dominator", "folder": "3rdClass", "xml": "Dominator"},
            "Warcryer": {"slug": "warcryer", "folder": "2ndClass", "xml": "Warcryer"},
            "Doomcryer": {"slug": "doomcryer", "folder": "3rdClass", "xml": "Doomcryer"},
            # --- Orc Lancer (Vanguard) ---
            "Orc Lancer": {"slug": "orc_rider_0", "folder": "Vanguard", "xml": "OrcLancer"},
            "Rider": {"slug": "orc_rider_1", "folder": "Vanguard", "xml": "OrcRider"},
            "Dragoon": {"slug": "orc_rider_2", "folder": "Vanguard", "xml": "Dragoon"},
            "Vanguard Raider": {"slug": "orc_rider_3", "folder": "Vanguard", "xml": "VanguardRaider"},
            # --- Dwarven ---
            "Dwarven Fighter": {"slug": "dwarven_fighter", "folder": "StartingClass", "xml": "DwarvenFighter"},
            "Scavenger": {"slug": "scavenger", "folder": "1stClass", "xml": "Scavenger"},
            "Bounty Hunter": {"slug": "bounty_hunter", "folder": "2ndClass", "xml": "BountyHunter"},
            "Fortune Seeker": {"slug": "fortune_seeker", "folder": "3rdClass", "xml": "FortuneSeeker"},
            "Artisan": {"slug": "artisan", "folder": "1stClass", "xml": "Artisan"},
            "Warsmith": {"slug": "warsmith", "folder": "2ndClass", "xml": "Warsmith"},
            "Maestro": {"slug": "maestro", "folder": "3rdClass", "xml": "Maestro"},            
            # --- Kamael ---
            "Kamael Soldier": {"slug": "jin_kamael_soldier", "folder": "Kamael", "xml": "KamaelSoldier"},
            "Trooper": {"slug": "trooper", "folder": "Kamael", "xml": "KamaelTrooper"},
            "Berserker": {"slug": "berserker", "folder": "Kamael", "xml": "KamaelBerserker"},
            "Doombringer": {"slug": "doombringer", "folder": "Kamael", "xml": "KamaelDoombringer"},
            "Soul Finder": {"slug": "soul_finder", "folder": "Kamael", "xml": "KamaelSoulFinder"},
            "Soul Breaker": {"slug": "soul_breaker", "folder": "Kamael", "xml": "KamaelSoulBreaker"},
            "Soul Hound": {"slug": "soul_hound", "folder": "Kamael", "xml": "KamaelSoulHound"},
            "Warder": {"slug": "warder", "folder": "Kamael", "xml": "KamaelWarder"},
            "Soul Ranger": {"slug": "soul_ranger", "folder": "Kamael", "xml": "KamaelSoulRanger"},
            "Trickster": {"slug": "trickster", "folder": "Kamael", "xml": "KamaelTrickster"},
            # --- Samurai ---
            "Ashigaru": {"slug": "crow_0", "folder": "Samurai", "xml": "Ashigaru"},
            "Hatamoto": {"slug": "crow_1", "folder": "Samurai", "xml": "Hatamoto"},
            "Ronin": {"slug": "crow_2", "folder": "Samurai", "xml": "Ronin"},
            "Samurai": {"slug": "crow_3", "folder": "Samurai", "xml": "Samurai"},
            # --- Sylph ---
            "Sylph Gunner": {"slug": "sylphid", "folder": "Sylph", "xml": "SylphGunner"},
            "Sharpshooter": {"slug": "sylph_gunner", "folder": "Sylph", "xml": "Sharpshooter"},
            "Wind Sniper": {"slug": "wind_hunter", "folder": "Sylph", "xml": "WindSniper"},
            "Storm Blaster": {"slug": "storm_blaster", "folder": "Sylph", "xml": "StormBlaster"},
            # --- High Elf (Divine Templar) ---
            "Divine Templar - 1": {"slug": "sacred_templar_0", "folder": "HighElf", "xml": "DivineTemplar0"},
            "Divine Templar - 2": {"slug": "sacred_templar_1", "folder": "HighElf", "xml": "DivineTemplar1"},
            "Divine Templar - 3": {"slug": "sacred_templar_2", "folder": "HighElf", "xml": "DivineTemplar2"},
            "Divine Templar - 4": {"slug": "sacred_templar_3", "folder": "HighElf", "xml": "DivineTemplar3"},
            # --- High Elf (Element Weaver) ---
            "Element Weaver - 1": {"slug": "spirit_0", "folder": "HighElf", "xml": "ElementWeaver0"},
            "Element Weaver - 2": {"slug": "spirit_1", "folder": "HighElf", "xml": "ElementWeaver1"},
            "Element Weaver - 3": {"slug": "spirit_2", "folder": "HighElf", "xml": "ElementWeaver2"},
            "Element Weaver - 4": {"slug": "spirit_3", "folder": "HighElf", "xml": "ElementWeaver3"},
        }

        # Class Mapping "Main"
        self.class_mapping_main = {
            "Sigel Phoenix Knight": {"slug": "sigel_phoenix_knight", "folder": "4rthClass", "xml": "SigelPhoenixKnight"},
            "Sigel Hell Knight": {"slug": "sigel_hell_knight", "folder": "4rthClass", "xml": "SigelHellKnight"},
            "Sigel Eva's Templar": {"slug": "sigel_evas_templar", "folder": "4rthClass", "xml": "SigelEva'sTemplar"},
            "Sigel Shillien Templar": {"slug": "sigel_shilien_templar", "folder": "4rthClass", "xml": "SigelShillienTemplar"},
            "Sigel Dark Knight": {"slug": "sigel_dark_knight", "folder": "4rthClass", "xml": "SigelDarkKnight"},
            "Tyrr Duelist": {"slug": "tir_duelist", "folder": "4rthClass", "xml": "TyrrDuelist"},
            "Tyrr Dreadnought": {"slug": "tir_dreadnought", "folder": "4rthClass", "xml": "TyrrDreadnought"},
            "Tyrr Titan": {"slug": "tir_titan", "folder": "4rthClass", "xml": "TyrrTitan"},
            "Tyrr Grand Khavatari": {"slug": "tir_grand_khavatari", "folder": "4rthClass", "xml": "TyrrGrandKhavatari"},
            "Tyrr Maestro": {"slug": "tir_maestro", "folder": "4rthClass", "xml": "TyrrMaestro"},
            "Tyrr Doombringer": {"slug": "tir_doombringer", "folder": "4rthClass", "xml": "TyrrDoombringer"},
            "Eviscerator": {"slug": "strato_lenker", "folder": "Ertheia", "xml": "Eviscerator"},
            "Warg": {"slug": "wolf_waker", "folder": "Warg", "xml": "Warg4"},
            "Samurai Main": {"slug": "true_crow", "folder": "Samurai", "xml": "Samurai"},
            "Othell Adventurer": {"slug": "othel_adventurer", "folder": "4rthClass", "xml": "OthellAdventurer"},
            "Othell Wind Rider": {"slug": "othel_wind_rider", "folder": "4rthClass", "xml": "OthellWindRider"},
            "Othell Ghost Hunter": {"slug": "othel_ghost_hunter", "folder": "4rthClass", "xml": "OthellGhostHunter"},
            "Othell Fortune Seeker": {"slug": "othel_fortune_seeker", "folder": "4rthClass", "xml": "OthellFortuneSeeker"},
            "Yul Sagittarius": {"slug": "yr_sagittarius", "folder": "4rthClass", "xml": "YulSaggitarius"},
            "Yul Moonlight Sentinel": {"slug": "yr_moonlight_sentinel", "folder": "4rthClass", "xml": "YulMoonlightSentinel"},
            "Yul Ghost Sentinel": {"slug": "yr_ghost_sentinel", "folder": "4rthClass", "xml": "YulGhostSentinel"},
            "Yul Trickster": {"slug": "yr_trickster", "folder": "4rthClass", "xml": "YulTrickster"},
            "Feoh Archmage": {"slug": "feoh_archmage", "folder": "4rthClass", "xml": "FeohArchmage"},
            "Feoh Soultaker": {"slug": "feoh_soultaker", "folder": "4rthClass", "xml": "FeohSoultaker"},
            "Feoh Mystic Muse": {"slug": "feoh_mystic_muse", "folder": "4rthClass", "xml": "FeohMysticMuse"},
            "Feoh Storm Screamer": {"slug": "feoh_storm_screamer", "folder": "4rthClass", "xml": "FeohStormScreamer"},
            "Feoh Soul Hound": {"slug": "feoh_soul_hound", "folder": "4rthClass", "xml": "FeohSoulHound"},
            "Sayha's Seer": {"slug": "sayhas_seer", "folder": "Ertheia", "xml": "Sayha'sSeer"},
            "Shine Maker": {"slug": "shine_maker", "folder": "ShineMaker", "xml": "ShineMaker"},
            "Wynn Arcana Lord": {"slug": "wynn_arcana_lord", "folder": "4rthClass", "xml": "WynnArcanaLord"},
            "Wynn Elemental Master": {"slug": "wynn_elemental_master", "folder": "4rthClass", "xml": "WynnElementalMaster"},
            "Wynn Spectral Master": {"slug": "wynn_spectral_master", "folder": "4rthClass", "xml": "WynnSpectralMaster"},
            "Aeore Cardinal": {"slug": "eolh_cardinal", "folder": "4rthClass", "xml": "AeoreCardinal"},
            "Aeore Eva's Saint": {"slug": "eolh_evas_saint", "folder": "4rthClass", "xml": "AeoreEva'sSaint"},
            "Aeore Shillien Saint": {"slug": "eolh_shilien_saint", "folder": "4rthClass", "xml": "AeoreShillienSaint"},
            "Iss Hierophant": {"slug": "is_hierophant", "folder": "4rthClass", "xml": "IssHierophant"},
            "Iss Sword Muse": {"slug": "is_sword_muse", "folder": "4rthClass", "xml": "IssSwordMuse"},
            "Iss Spectral Dancer": {"slug": "is_spectral_dancer", "folder": "4rthClass", "xml": "IssSpectralDancer"},
        }
        
        self.class_mapping_actual = self.class_mapping_main
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        controls_group = QGroupBox("Configuration")
        controls_layout = QGridLayout(controls_group)
        
        controls_layout.addWidget(QLabel("Site:"), 0, 0)
        self.site_combo = QComboBox()
        self.site_combo.addItems(["main", "essence"])
        self.site_combo.currentTextChanged.connect(self.on_site_changed)
        controls_layout.addWidget(self.site_combo, 0, 1)
        
        controls_layout.addWidget(QLabel("Select Class:"), 1, 0)
        self.class_combo = QComboBox()
        controls_layout.addWidget(self.class_combo, 1, 1)
        self.class_combo.currentTextChanged.connect(self.on_class_mapping_changed)

        self.info_label = QLabel("Ready to map...")
        self.info_label.setStyleSheet("color: #777; font-family: 'Consolas'; font-size: 11px;")
        controls_layout.addWidget(self.info_label, 2, 1)
        
        action_layout = QHBoxLayout()
        self.start_btn = QPushButton("🚀 Start Deep Scraping")
        self.stop_btn = QPushButton("🛑 Stop")
        self.clear_log_btn = QPushButton("🗑️ Clear Log")
        self.stop_btn.setEnabled(False)
        
        action_layout.addWidget(self.start_btn)
        action_layout.addWidget(self.stop_btn)
        action_layout.addWidget(self.clear_log_btn)
        
        progress_layout = QVBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.status_label = QLabel("Ready - Deep Scraper Idle")
        self.status_label.setStyleSheet("color: #555; font-weight: bold;")
        
        progress_layout.addWidget(QLabel("Current Task Progress:"))
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.status_label)
        
        stats_group = QGroupBox("📊 SkillTree Analysis")
        stats_layout = QVBoxLayout(stats_group)
        general_grid = QGridLayout()
        
        self.current_class_label = QLabel("Current Class: -")
        self.categories_label = QLabel("Categories: 0")
        self.site_skills_label = QLabel("Active Skills: 0")
        self.xml_skills_label = QLabel("XML Skills: 0")
        self.removed_label = QLabel("🔴 Removed IDs: 0")
        self.removed_label.setStyleSheet("color: #d32f2f; font-weight: bold;")
        
        general_grid.addWidget(self.current_class_label, 0, 0)
        general_grid.addWidget(self.removed_label, 0, 1)
        general_grid.addWidget(self.categories_label, 1, 0)
        general_grid.addWidget(self.site_skills_label, 1, 1)
        general_grid.addWidget(self.xml_skills_label, 2, 0)
        
        stats_layout.addLayout(general_grid)
        stats_layout.addWidget(QFrame(frameShape=QFrame.Shape.HLine))
        
        self.categories_detail_label = QLabel("Categories breakdown:\n(waiting for index...)")
        self.categories_detail_label.setStyleSheet("font-family: 'Consolas', monospace; color: #2e7d32;")
        stats_layout.addWidget(self.categories_detail_label)
        
        log_group = QGroupBox("Execution Log")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background-color: #1e1e1e; color: #dcdcdc; font-family: 'Consolas';")
        log_layout.addWidget(self.log_text)
        
        layout.addWidget(controls_group)
        layout.addLayout(action_layout)
        layout.addLayout(progress_layout)
        layout.addWidget(stats_group)
        layout.addWidget(log_group, 1)
        
        self.setup_connections()
        self.update_class_dropdown() # Inicializa as classes pela primeira vez

    def setup_connections(self):
        self.start_btn.clicked.connect(self.start_scraping)
        self.stop_btn.clicked.connect(self.stop_scraping)
        self.clear_log_btn.clicked.connect(self.log_text.clear)

    def on_site_changed(self, site_type):
        self.site_type = site_type
        self.log(f"🌐 Site context: {site_type.upper()}")
        self.update_class_dropdown()

    def update_class_dropdown(self):
        """Atualiza a lista de classes disponível no dropdown baseado no site selecionado"""
        self.class_combo.blockSignals(True)
        self.class_combo.clear()
        
        if self.site_type == "main":
            self.class_mapping_actual = self.class_mapping_main
        else:
            self.class_mapping_actual = self.class_mapping_essence
            
        self.class_combo.addItems(sorted(self.class_mapping_actual.keys()))
        self.class_combo.blockSignals(False)
        
        # Dispara a atualização manual da informação técnica
        self.on_class_mapping_changed(self.class_combo.currentText())

    def on_class_mapping_changed(self, class_display_name):
        if not class_display_name:
            return
            
        mapping = self.class_mapping_actual.get(class_display_name)
        if mapping:
            self.current_slug = mapping['slug']
            self.current_folder = mapping['folder']
            self.current_xml = mapping['xml']
            
            site_name = "Main" if self.site_type == "main" else "Essence"
            self.info_label.setText(f"Target -> Slug: {self.current_slug} | Folder: {site_name}/{self.current_folder} | XML: {self.current_xml}.xml")

    def start_scraping(self):
        if not hasattr(self, 'current_slug'): return
        
        self.log(f"--- Starting Deep Scrape: {self.class_combo.currentText()} ---")
        
        # Verifique se o Worker está importado corretamente
        try:
            from workers.skilltree_scraper import SkillTreeScraperWorker
            self.scraper_worker = SkillTreeScraperWorker(
                site_type=self.site_type.upper(),
                class_slug=self.current_slug,
                xml_folder=self.current_folder,
                xml_class_name=self.current_xml,
                max_workers=5
            )
            
            self.scraper_worker.log_signal.connect(self.log)
            self.scraper_worker.progress_signal.connect(self.update_progress)
            self.scraper_worker.stats_signal.connect(self.update_stats)
            self.scraper_worker.audit_signal.connect(self.on_audit_entry)
            self.scraper_worker.finished_signal.connect(self.scraping_finished)
            self.scraper_worker.finished.connect(self.on_worker_finished)
            
            self.scraper_worker.start()
            self.update_controls(True)
            self.current_class_label.setText(f"Current Class: {self.class_combo.currentText()}")
            self.progress_bar.setMaximum(0)
        except Exception as e:
            self.log(f"Error starting worker: {str(e)}")

    def update_progress(self, current, total, status):
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
            percent = (current / total) * 100
            self.status_label.setText(f"[{percent:.1f}%] {status}")
        else:
            self.status_label.setText(status)

    def update_stats(self, stats_data):
        self.site_skills_label.setText(f"Active Skills: {stats_data.get('total_skills', 0)}")
        self.removed_label.setText(f"🔴 Removed IDs: {stats_data.get('total_removed_found', 0)}")
        self.categories_label.setText(f"Categories: {stats_data.get('total_categories', 0)}")
        self.xml_skills_label.setText(f"XML Skills: {stats_data.get('xml_total_skills', 0)}")

        breakdown = stats_data.get('skills_by_category', {})
        if breakdown:
            text = "Categories breakdown:\n"
            for cat, count in breakdown.items():
                text += f"  > {cat.replace('_', ' ').title()}: {count}\n"
            self.categories_detail_label.setText(text)

    def on_audit_entry(self, audit_data):
        removed_ids = audit_data.get('removed_session', {}).get('ids', [])
        self.log("\n" + "═"*50)
        self.log("<b style='color: #FF5722;'>📋 FINAL AUDIT SUMMARY</b>")
        self.log(f"IDs marked for removal: {', '.join(removed_ids) if removed_ids else 'None'}")
        self.log("═"*50 + "\n")

    def scraping_finished(self, final_stats):
        self.log("✅ Deep Scraping Process Completed!")
        self.status_label.setText("Success - Data ready")

    def log(self, message):
        self.log_text.append(f"[{time.strftime('%H:%M:%S')}] {message}")
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)

    def stop_scraping(self):
        if self.scraper_worker:
            self.scraper_worker.stop()
            self.log("🛑 Termination requested...")

    def update_controls(self, running):
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.class_combo.setEnabled(not running)
        self.site_combo.setEnabled(not running)

    def on_worker_finished(self):
        self.update_controls(False)