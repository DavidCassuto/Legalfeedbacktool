"""
AI-gebaseerde feedback module voor document secties.
Gebruikt Google Gemini API voor het genereren van intelligente feedback.
"""

import os
import json
import google.generativeai as genai
from typing import List, Dict, Any, Optional
import logging

# Configureer logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AIFeedbackGenerator:
    """AI feedback generator die Gemini API gebruikt voor intelligente feedback op document secties."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialiseer de AI feedback generator.
        
        Args:
            api_key: Gemini API key. Als None, wordt gezocht naar GEMINI_API_KEY environment variable.
        """
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("Gemini API key is vereist. Stel GEMINI_API_KEY environment variable in of geef api_key parameter.")
        
        # Configureer Gemini
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Feedback templates voor verschillende secties
        self.feedback_templates = {
            'inleiding': {
                'system_prompt': """Je bent een expert docent die feedback geeft op academische documenten. 
                Analyseer de inleiding van het document en geef constructieve feedback op:
                - Duidelijkheid en structuur
                - Probleemstelling en context
                - Leesbaarheid en flow
                - Academische stijl
                
                Geef specifieke, praktische suggesties voor verbetering.""",
                'max_tokens': 500
            },
            'probleemanalyse': {
                'system_prompt': """Je bent een expert docent die feedback geeft op academische documenten.
                Analyseer de probleemanalyse sectie en geef feedback op:
                - Duidelijke probleemformulering
                - Relevante context en achtergrond
                - Logische structuur
                - Bewijslast en onderbouwing
                
                Geef concrete suggesties voor verbetering.""",
                'max_tokens': 500
            },
            'methode': {
                'system_prompt': """Je bent een expert docent die feedback geeft op academische documenten.
                Analyseer de methode sectie en geef feedback op:
                - Duidelijkheid van onderzoeksopzet
                - Beschrijving van dataverzameling
                - Methodologische keuzes en onderbouwing
                - Reproduceerbaarheid
                
                Geef praktische verbeteringssuggesties.""",
                'max_tokens': 500
            },
            'resultaten': {
                'system_prompt': """Je bent een expert docent die feedback geeft op academische documenten.
                Analyseer de resultaten sectie en geef feedback op:
                - Duidelijke presentatie van bevindingen
                - Relevante data en analyses
                - Interpretatie van resultaten
                - Visuele ondersteuning (indien van toepassing)
                
                Geef suggesties voor verbetering.""",
                'max_tokens': 500
            },
            'discussie': {
                'system_prompt': """Je bent een expert docent die feedback geeft op academische documenten.
                Analyseer de discussie sectie en geef feedback op:
                - Diepte van analyse
                - Kritische reflectie
                - Verbinding met literatuur
                - Implicaties en beperkingen
                
                Geef constructieve feedback voor verbetering.""",
                'max_tokens': 500
            },
            'conclusie': {
                'system_prompt': """Je bent een expert docent die feedback geeft op academische documenten.
                Analyseer de conclusie sectie en geef feedback op:
                - Samenvatting van belangrijkste bevindingen
                - Beantwoording van onderzoeksvragen
                - Praktische implicaties
                - Aanbevelingen voor vervolgonderzoek
                
                Geef suggesties voor verbetering.""",
                'max_tokens': 400
            }
        }
    
    def generate_section_feedback(self, section_name: str, section_content: str, 
                                 document_type: str = "academisch rapport") -> Dict[str, Any]:
        """
        Genereer AI feedback voor een specifieke sectie.
        
        Args:
            section_name: Naam van de sectie (bijv. 'inleiding', 'methode')
            section_content: Inhoud van de sectie
            document_type: Type document voor context
            
        Returns:
            Dict met feedback informatie
        """
        try:
            # Bepaal template op basis van sectie naam
            template_key = self._get_template_key(section_name)
            template = self.feedback_templates.get(template_key, self.feedback_templates['inleiding'])
            
            # Bouw de prompt
            prompt = self._build_feedback_prompt(
                section_name=section_name,
                section_content=section_content,
                document_type=document_type,
                system_prompt=template['system_prompt']
            )
            
            # Genereer feedback via Gemini
            response = self.model.generate_content(prompt)
            
            if response.text:
                # Parse de feedback
                feedback_data = self._parse_ai_response(response.text, section_name)
                return feedback_data
            else:
                logger.warning(f"Geen response van Gemini voor sectie: {section_name}")
                return self._create_fallback_feedback(section_name, "Kon geen AI feedback genereren.")
                
        except Exception as e:
            logger.error(f"Fout bij genereren AI feedback voor sectie {section_name}: {e}")
            return self._create_fallback_feedback(section_name, f"Fout bij AI feedback: {str(e)}")
    
    def _get_template_key(self, section_name: str) -> str:
        """Bepaal welke template te gebruiken op basis van sectie naam."""
        section_lower = section_name.lower()
        
        # Mapping van sectie namen naar template keys
        mappings = {
            'inleiding': 'inleiding',
            'introduction': 'inleiding',
            'probleemanalyse': 'probleemanalyse',
            'probleemstelling': 'probleemanalyse',
            'problem statement': 'probleemanalyse',
            'methode': 'methode',
            'methodology': 'methode',
            'method': 'methode',
            'resultaten': 'resultaten',
            'results': 'resultaten',
            'discussie': 'discussie',
            'discussion': 'discussie',
            'conclusie': 'conclusie',
            'conclusion': 'conclusie'
        }
        
        return mappings.get(section_lower, 'inleiding')
    
    def _build_feedback_prompt(self, section_name: str, section_content: str, 
                              document_type: str, system_prompt: str) -> str:
        """Bouw de prompt voor Gemini."""
        return f"""{system_prompt}

DOCUMENT TYPE: {document_type}
SECTIE: {section_name}

SECTIE INHOUD:
{section_content}

Geef je feedback in het volgende JSON formaat:
{{
    "overall_score": 1-10,
    "strengths": ["sterkte 1", "sterkte 2"],
    "weaknesses": ["zwakte 1", "zwakte 2"],
    "suggestions": ["suggestie 1", "suggestie 2"],
    "summary": "Korte samenvatting van de feedback"
}}

Zorg dat je feedback constructief, specifiek en praktisch is."""
    
    def _parse_ai_response(self, response_text: str, section_name: str) -> Dict[str, Any]:
        """Parse de AI response naar gestructureerde feedback."""
        try:
            # Probeer JSON te parsen
            if '{' in response_text and '}' in response_text:
                start = response_text.find('{')
                end = response_text.rfind('}') + 1
                json_str = response_text[start:end]
                feedback_data = json.loads(json_str)
                
                return {
                    'section_name': section_name,
                    'overall_score': feedback_data.get('overall_score', 5),
                    'strengths': feedback_data.get('strengths', []),
                    'weaknesses': feedback_data.get('weaknesses', []),
                    'suggestions': feedback_data.get('suggestions', []),
                    'summary': feedback_data.get('summary', 'Geen samenvatting beschikbaar'),
                    'raw_response': response_text,
                    'ai_generated': True
                }
            else:
                # Fallback als geen JSON gevonden
                return self._create_fallback_feedback(section_name, response_text)
                
        except json.JSONDecodeError as e:
            logger.warning(f"Kon AI response niet parsen als JSON: {e}")
            return self._create_fallback_feedback(section_name, response_text)
    
    def _create_fallback_feedback(self, section_name: str, message: str) -> Dict[str, Any]:
        """Maak fallback feedback als AI generatie faalt."""
        return {
            'section_name': section_name,
            'overall_score': 5,
            'strengths': [],
            'weaknesses': ['Kon geen AI feedback genereren'],
            'suggestions': ['Controleer de sectie handmatig'],
            'summary': message,
            'raw_response': message,
            'ai_generated': False
        }
    
    def generate_document_overview(self, sections_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Genereer een overzicht van het hele document op basis van alle secties.
        
        Args:
            sections_data: Lijst van sectie data met AI feedback
            
        Returns:
            Dict met document overzicht
        """
        try:
            # Bouw overzicht van alle secties
            sections_summary = []
            total_score = 0
            valid_sections = 0
            
            for section in sections_data:
                if section.get('ai_generated', False):
                    sections_summary.append({
                        'name': section['section_name'],
                        'score': section['overall_score'],
                        'summary': section['summary']
                    })
                    total_score += section['overall_score']
                    valid_sections += 1
            
            avg_score = total_score / valid_sections if valid_sections > 0 else 5
            
            # Genereer document-level feedback
            prompt = f"""Je bent een expert docent die een eindbeoordeling geeft van een academisch document.

DOCUMENT OVERZICHT:
{json.dumps(sections_summary, indent=2)}

Gemiddelde score: {avg_score:.1f}/10

Geef een eindbeoordeling in het volgende JSON formaat:
{{
    "overall_assessment": "Algemene beoordeling van het document",
    "main_strengths": ["sterkte 1", "sterkte 2"],
    "main_weaknesses": ["zwakte 1", "zwakte 2"],
    "priority_improvements": ["verbetering 1", "verbetering 2"],
    "final_grade": "A/B/C/D/F of percentage",
    "recommendations": "Algemene aanbevelingen voor verbetering"
}}"""
            
            response = self.model.generate_content(prompt)
            
            if response.text:
                # Parse document feedback
                if '{' in response.text and '}' in response.text:
                    start = response.text.find('{')
                    end = response.text.rfind('}') + 1
                    json_str = response.text[start:end]
                    doc_feedback = json.loads(json_str)
                    
                    return {
                        'overall_assessment': doc_feedback.get('overall_assessment', 'Geen beoordeling'),
                        'main_strengths': doc_feedback.get('main_strengths', []),
                        'main_weaknesses': doc_feedback.get('main_weaknesses', []),
                        'priority_improvements': doc_feedback.get('priority_improvements', []),
                        'final_grade': doc_feedback.get('final_grade', 'C'),
                        'recommendations': doc_feedback.get('recommendations', 'Geen aanbevelingen'),
                        'average_score': avg_score,
                        'sections_analyzed': valid_sections,
                        'ai_generated': True
                    }
            
            return self._create_fallback_document_feedback(avg_score, valid_sections)
            
        except Exception as e:
            logger.error(f"Fout bij genereren document overzicht: {e}")
            return self._create_fallback_document_feedback(5, 0)
    
    def _create_fallback_document_feedback(self, avg_score: float, sections_count: int) -> Dict[str, Any]:
        """Maak fallback document feedback."""
        return {
            'overall_assessment': 'Kon geen document overzicht genereren',
            'main_strengths': [],
            'main_weaknesses': ['AI feedback niet beschikbaar'],
            'priority_improvements': ['Controleer document handmatig'],
            'final_grade': 'C',
            'recommendations': 'Gebruik handmatige beoordeling',
            'average_score': avg_score,
            'sections_analyzed': sections_count,
            'ai_generated': False
        } 