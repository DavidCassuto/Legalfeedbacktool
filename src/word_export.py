"""
Word document export module.
Voegt feedback toe aan het originele Word document als comments.
"""

import os
import copy
from typing import List, Dict, Any, Optional, Tuple
from docx import Document
from docx.shared import Inches, RGBColor
from docx.enum.text import WD_COLOR_INDEX
from docx.oxml.shared import OxmlElement, qn
from docx.oxml.ns import nsdecls
from docx.oxml import parse_xml
import logging

# Import nieuwe Word comments module
try:
    from word_comments import WordCommentManager
except ImportError:
    # Fallback voor als de module niet gevonden wordt
    from .word_comments import WordCommentManager

logger = logging.getLogger(__name__)

class WordFeedbackExporter:
    """Exporteert feedback naar Word document als comments."""
    
    def __init__(self):
        """Initialiseer de Word export module."""
        self.comment_id_counter = 1
    
    def add_feedback_to_document(self, original_file_path: str, feedback_data: Dict[str, Any], 
                                output_file_path: Optional[str] = None, use_real_comments: bool = True) -> str:
        """
        Voeg feedback toe aan het originele Word document als comments.
        
        Args:
            original_file_path: Pad naar het originele Word document
            feedback_data: Dictionary met feedback data
            output_file_path: Pad voor het output document (optioneel)
            use_real_comments: Gebruik echte Word comments (True) of tekst-based feedback (False)
            
        Returns:
            Pad naar het aangepaste document
        """
        try:
            if use_real_comments:
                # Gebruik nieuwe sectie-specifieke Word comments
                logger.info("Gebruik sectie-specifieke Word comments...")
                comment_manager = WordCommentManager()
                
                # Haal sectie data op uit feedback_data
                sections_data = feedback_data.get('sections', [])
                
                # Converteer feedback naar het juiste formaat voor sectie-specifieke comments
                formatted_feedback = {
                    'feedback': feedback_data.get('feedback_items', [])
                }
                
                return comment_manager.add_section_specific_comments(
                    original_file_path, formatted_feedback, sections_data, output_file_path
                )
            else:
                # Gebruik oude tekst-based aanpak
                logger.info("Gebruik tekst-based feedback...")
                return self._add_text_based_feedback(original_file_path, feedback_data, output_file_path)
            
        except Exception as e:
            logger.error(f"Fout bij toevoegen feedback aan Word document: {e}")
            raise
    
    def _add_text_based_feedback(self, original_file_path: str, feedback_data: Dict[str, Any], 
                                output_file_path: Optional[str] = None) -> str:
        """Oude tekst-based feedback implementatie."""
        try:
            # Open het originele document
            doc = Document(original_file_path)
            
            # Reset comment counter
            self.comment_id_counter = 1
            
            # Voeg feedback toe per sectie
            sections = feedback_data.get('sections', [])
            feedback_items = feedback_data.get('feedback_items', [])
            
            # Groepeer feedback per sectie
            feedback_by_section = {}
            for item in feedback_items:
                section_name = item.get('section_name', 'Algemeen')
                if section_name not in feedback_by_section:
                    feedback_by_section[section_name] = []
                feedback_by_section[section_name].append(item)
            
            # Voeg comments toe aan secties
            for section in sections:
                if section.get('found', False):
                    section_name = section.get('name', '')
                    section_feedback = feedback_by_section.get(section_name, [])
                    if section_feedback:
                        self._add_section_comments_simple(doc, section, section_feedback)
            
            # Voeg algemene feedback toe aan het begin van het document
            general_feedback = feedback_by_section.get('Algemeen', [])
            if general_feedback:
                self._add_general_comments_simple(doc, general_feedback)
            
            # Bepaal output pad
            if not output_file_path:
                base_name = os.path.splitext(original_file_path)[0]
                output_file_path = f"{base_name}_met_feedback.docx"
            
            # Sla het aangepaste document op
            doc.save(output_file_path)
            logger.info(f"Document met tekst-based feedback opgeslagen: {output_file_path}")
            
            return output_file_path
            
        except Exception as e:
            logger.error(f"Fout bij toevoegen tekst-based feedback: {e}")
            raise
    
    def _add_section_comments_simple(self, doc: Document, section: Dict[str, Any], feedback_items: List[Dict[str, Any]]):
        """Voeg comments toe aan een specifieke sectie met eenvoudige aanpak."""
        section_name = section.get('name', 'Onbekende sectie')
        
        # Zoek de sectie heading in het document
        section_heading = self._find_section_heading(doc, section_name)
        
        if section_heading:
            # Voeg comment toe aan de sectie heading
            comment_text = self._format_section_feedback(section_name, feedback_items)
            self._add_comment_simple(section_heading, comment_text)
        else:
            # Als sectie niet gevonden, voeg toe aan eerste paragraaf
            if doc.paragraphs:
                comment_text = self._format_section_feedback(section_name, feedback_items)
                self._add_comment_simple(doc.paragraphs[0], comment_text)
    
    def _add_general_comments_simple(self, doc: Document, feedback_items: List[Dict[str, Any]]):
        """Voeg algemene feedback toe aan het begin van het document."""
        if doc.paragraphs:
            comment_text = self._format_general_feedback(feedback_items)
            self._add_comment_simple(doc.paragraphs[0], comment_text)
    
    def _find_section_heading(self, doc: Document, section_name: str):
        """Zoek een sectie heading in het document."""
        for paragraph in doc.paragraphs:
            if paragraph.style.name.startswith('Heading'):
                heading_text = paragraph.text.lower()
                if section_name.lower() in heading_text:
                    return paragraph
        return None
    
    def _add_comment_simple(self, paragraph, comment_text: str):
        """Voeg een comment toe aan een paragraaf met eenvoudige aanpak."""
        try:
            # Voeg comment toe als tekst met speciale formatting
            comment_run = paragraph.add_run(f" [Feedback: {comment_text}]")
            comment_run.font.color.rgb = RGBColor(128, 128, 128)  # Grijs
            comment_run.italic = True
            comment_run.font.size = Inches(0.1)  # Kleine tekst
            
        except Exception as e:
            logger.warning(f"Kon comment niet toevoegen: {e}")
            # Fallback: voeg feedback toe als gewone tekst
            paragraph.add_run(f" [Feedback: {comment_text}]")
    
    def _format_section_feedback(self, section_name: str, feedback_items: List[Dict[str, Any]]) -> str:
        """Format feedback items voor een sectie."""
        if not feedback_items:
            return f"Geen feedback voor sectie '{section_name}'"
        
        feedback_lines = [f"Feedback voor sectie '{section_name}':"]
        
        for item in feedback_items:
            status = item.get('status', 'unknown')
            message = item.get('message', 'Geen bericht')
            suggestion = item.get('suggestion', '')
            criterion_name = item.get('criterion_name', 'Onbekend criterium')
            
            # Voeg status icon toe
            if status == 'error' or status == 'violation':
                feedback_lines.append(f"❌ {criterion_name}: {message}")
            elif status == 'warning':
                feedback_lines.append(f"⚠️ {criterion_name}: {message}")
            elif status == 'ok':
                feedback_lines.append(f"✅ {criterion_name}: {message}")
            else:
                feedback_lines.append(f"ℹ️ {criterion_name}: {message}")
            
            if suggestion:
                feedback_lines.append(f"   💡 Suggestie: {suggestion}")
        
        return "\n".join(feedback_lines)
    
    def _format_general_feedback(self, feedback_items: List[Dict[str, Any]]) -> str:
        """Format algemene feedback."""
        if not feedback_items:
            return "Geen algemene feedback"
        
        feedback_lines = ["Algemene feedback:"]
        
        for item in feedback_items:
            status = item.get('status', 'unknown')
            message = item.get('message', 'Geen bericht')
            suggestion = item.get('suggestion', '')
            criterion_name = item.get('criterion_name', 'Onbekend criterium')
            
            # Voeg status icon toe
            if status == 'error' or status == 'violation':
                feedback_lines.append(f"❌ {criterion_name}: {message}")
            elif status == 'warning':
                feedback_lines.append(f"⚠️ {criterion_name}: {message}")
            elif status == 'ok':
                feedback_lines.append(f"✅ {criterion_name}: {message}")
            else:
                feedback_lines.append(f"ℹ️ {criterion_name}: {message}")
            
            if suggestion:
                feedback_lines.append(f"   💡 Suggestie: {suggestion}")
        
        return "\n".join(feedback_lines)
    
    def create_feedback_summary_document(self, feedback_data: Dict[str, Any], 
                                       output_file_path: str) -> str:
        """
        Maak een nieuw Word document met alleen feedback samenvatting.
        
        Args:
            feedback_data: Dictionary met feedback data
            output_file_path: Pad voor het output document
            
        Returns:
            Pad naar het aangepaste document
        """
        try:
            # Maak een nieuw document
            doc = Document()
            
            # Voeg titel toe
            title = doc.add_heading("Document Feedback Rapport", level=0)
            title.style.font.color.rgb = RGBColor(0, 0, 139)  # Donkerblauw
            
            # Voeg feedback toe
            self._add_feedback_section(doc, feedback_data)
            
            # Sla het document op
            doc.save(output_file_path)
            logger.info(f"Feedback samenvatting opgeslagen: {output_file_path}")
            
            return output_file_path
            
        except Exception as e:
            logger.error(f"Fout bij maken feedback samenvatting: {e}")
            raise
    
    def _add_feedback_section(self, doc: Document, feedback_data: Dict[str, Any]):
        """Voeg een feedback sectie toe aan het einde van het document."""
        
        # Voeg een pagina-einde toe
        doc.add_page_break()
        
        # Voeg hoofding toe
        heading = doc.add_heading("Document Feedback & Analyse", level=1)
        heading.style.font.color.rgb = RGBColor(0, 0, 139)  # Donkerblauw
        
        # Voeg feedback items toe
        feedback_items = feedback_data.get('feedback_items', [])
        
        if feedback_items:
            # Groepeer feedback per status
            violations = [f for f in feedback_items if f.get('status') in ['error', 'violation']]
            warnings = [f for f in feedback_items if f.get('status') == 'warning']
            passed = [f for f in feedback_items if f.get('status') in ['ok', 'info']]
            
            # Voeg statistieken toe
            stats_para = doc.add_paragraph()
            stats_para.add_run("📊 Feedback Overzicht:\n").bold = True
            stats_para.add_run(f"❌ Overtredingen: {len(violations)}\n")
            stats_para.add_run(f"⚠️ Waarschuwingen: {len(warnings)}\n")
            stats_para.add_run(f"✅ Correct: {len(passed)}\n")
            stats_para.add_run(f"📋 Totaal: {len(feedback_items)}")
            
            # Voeg gedetailleerde feedback toe
            if violations:
                doc.add_heading("❌ Overtredingen", level=2)
                for item in violations:
                    self._add_feedback_item(doc, item, "red")
            
            if warnings:
                doc.add_heading("⚠️ Waarschuwingen", level=2)
                for item in warnings:
                    self._add_feedback_item(doc, item, "orange")
            
            if passed:
                doc.add_heading("✅ Correct", level=2)
                for item in passed:
                    self._add_feedback_item(doc, item, "green")
        else:
            doc.add_paragraph("Geen feedback items gevonden.")
        
        # Voeg sectie informatie toe
        sections = feedback_data.get('sections', [])
        if sections:
            doc.add_page_break()
            doc.add_heading("📋 Sectie Analyse", level=1)
            
            for section in sections:
                self._add_section_info(doc, section)
        
        # Voeg AI feedback toe als die er is
        ai_feedback = feedback_data.get('ai_feedback', {})
        if ai_feedback:
            doc.add_page_break()
            doc.add_heading("🤖 AI Feedback", level=1)
            self._add_ai_feedback(doc, ai_feedback)
    
    def _add_feedback_item(self, doc: Document, item: Dict[str, Any], color: str):
        """Voeg een individueel feedback item toe."""
        para = doc.add_paragraph()
        
        # Criterium naam
        criterion_name = item.get('criterion_name', 'Onbekend criterium')
        section_name = item.get('section_name', 'Onbekende sectie')
        
        run = para.add_run(f"🔍 {criterion_name}")
        run.bold = True
        if color == "red":
            run.font.color.rgb = RGBColor(220, 20, 60)  # Crimson
        elif color == "orange":
            run.font.color.rgb = RGBColor(255, 140, 0)  # Dark Orange
        elif color == "green":
            run.font.color.rgb = RGBColor(34, 139, 34)  # Forest Green
        
        para.add_run(f" (Sectie: {section_name})\n")
        
        # Bericht
        message = item.get('message', 'Geen bericht')
        para.add_run(f"💬 {message}\n")
        
        # Suggestie
        suggestion = item.get('suggestion', '')
        if suggestion:
            suggestion_run = para.add_run(f"💡 Suggestie: {suggestion}\n")
            suggestion_run.italic = True
        
        # Locatie
        location = item.get('location', '')
        if location:
            para.add_run(f"📍 Locatie: {location}\n")
        
        # Confidence
        confidence = item.get('confidence', 0)
        if confidence > 0:
            para.add_run(f"🎯 Confidence: {confidence:.1%}\n")
        
        # Voeg een lege regel toe
        doc.add_paragraph()
    
    def _add_section_info(self, doc: Document, section: Dict[str, Any]):
        """Voeg sectie informatie toe."""
        para = doc.add_paragraph()
        
        section_name = section.get('name', 'Onbekende sectie')
        found = section.get('found', False)
        word_count = section.get('word_count', 0)
        confidence = section.get('confidence', 0)
        
        # Sectie naam en status
        status_icon = "✅" if found else "❌"
        status_text = "Gevonden" if found else "Niet gevonden"
        
        run = para.add_run(f"{status_icon} {section_name}")
        run.bold = True
        if found:
            run.font.color.rgb = RGBColor(34, 139, 34)  # Green
        else:
            run.font.color.rgb = RGBColor(220, 20, 60)  # Red
        
        para.add_run(f" - {status_text}\n")
        
        if found:
            para.add_run(f"📝 Woorden: {word_count}\n")
            if confidence > 0:
                para.add_run(f"🎯 Confidence: {confidence:.1%}\n")
        
        # Voeg een lege regel toe
        doc.add_paragraph()
    
    def _add_ai_feedback(self, doc: Document, ai_feedback: Dict[str, Any]):
        """Voeg AI feedback toe."""
        # Document-level AI feedback
        document_feedback = ai_feedback.get('document', {})
        if document_feedback:
            doc.add_heading("📄 Document Overzicht", level=2)
            para = doc.add_paragraph()
            para.add_run(document_feedback.get('summary', 'Geen AI feedback beschikbaar.'))
            doc.add_paragraph()
        
        # Sectie-level AI feedback
        sections_feedback = ai_feedback.get('sections', [])
        if sections_feedback:
            doc.add_heading("📋 Sectie Feedback", level=2)
            for section_feedback in sections_feedback:
                section_name = section_feedback.get('section_name', 'Onbekende sectie')
                feedback_text = section_feedback.get('feedback', 'Geen feedback beschikbaar.')
                
                para = doc.add_paragraph()
                run = para.add_run(f"🔍 {section_name}")
                run.bold = True
                run.font.color.rgb = RGBColor(0, 0, 139)  # Blue
                para.add_run(f"\n{feedback_text}")
                doc.add_paragraph() 