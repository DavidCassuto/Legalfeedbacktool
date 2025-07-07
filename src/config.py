"""
Configuratie bestand voor de Feedback Tool.
Bevat instellingen voor API keys en andere configuratie.
"""

import os
from typing import Optional

class Config:
    """Configuratie klasse voor de Feedback Tool."""
    
    # Flask configuratie
    SECRET_KEY = os.getenv('SECRET_KEY', 'feedback-tool-secret-key-2024')
    
    # Database configuratie
    DATABASE = os.getenv('DATABASE', 'instance/documents.db')
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'instance/uploads')
    
    # AI Feedback configuratie
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    
    # Export configuratie
    EXPORT_FOLDER = os.path.join(UPLOAD_FOLDER, 'exports')
    
    @classmethod
    def get_gemini_api_key(cls) -> Optional[str]:
        """Haal Gemini API key op."""
        return cls.GEMINI_API_KEY
    
    @classmethod
    def is_ai_feedback_enabled(cls) -> bool:
        """Check of AI feedback is ingeschakeld."""
        return bool(cls.GEMINI_API_KEY)
    
    @classmethod
    def validate_config(cls) -> list:
        """Valideer de configuratie en retourneer waarschuwingen."""
        warnings = []
        
        if not cls.GEMINI_API_KEY:
            warnings.append("GEMINI_API_KEY niet ingesteld. AI feedback zal niet beschikbaar zijn.")
        
        return warnings

# Maak export directory aan
os.makedirs(Config.EXPORT_FOLDER, exist_ok=True)
