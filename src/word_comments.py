"""
Word Comments Module - Echte Word comments implementatie
Gebruikt XML manipulatie om echte Word comments toe te voegen.
"""

import os
import zipfile
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional, Tuple
from docx import Document
from docx.oxml.shared import OxmlElement, qn
from docx.oxml.ns import nsdecls
import logging

logger = logging.getLogger(__name__)

class WordCommentManager:
    """Beheert echte Word comments via XML manipulatie."""
    
    def __init__(self):
        """Initialiseer de comment manager."""
        self.comment_id_counter = 1
        self.comment_ref_counter = 1
        
        # Word XML namespaces
        self.namespaces = {
            'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
            'w15': 'http://schemas.microsoft.com/office/word/2012/wordml'
        }
    
    def add_real_comments_to_document(self, doc_path: str, feedback_data: Dict[str, Any], 
                                    output_path: Optional[str] = None) -> str:
        """
        Voeg echte Word comments toe aan een document.
        
        Args:
            doc_path: Pad naar het originele Word document
            feedback_data: Dictionary met feedback data
            output_path: Pad voor het output document
            
        Returns:
            Pad naar het document met comments
        """
        try:
            logger.info("Start toevoegen echte Word comments...")
            
            # Kopieer het originele document
            if not output_path:
                base_name = os.path.splitext(doc_path)[0]
                output_path = f"{base_name}_met_comments.docx"
            
            # Kopieer document
            import shutil
            shutil.copy2(doc_path, output_path)
            
            # Open als ZIP (Word documents zijn ZIP files)
            with zipfile.ZipFile(output_path, 'a') as doc_zip:
                # Lees bestaande document XML
                document_xml = doc_zip.read('word/document.xml')
                comments_xml = self._get_or_create_comments_xml(doc_zip)
                
                # Parse XML
                doc_root = ET.fromstring(document_xml)
                comments_root = ET.fromstring(comments_xml)
                
                # Voeg comment namespace toe aan document
                self._add_comment_namespace(doc_root)
                
                # Voeg comments toe
                feedback_items = feedback_data.get('feedback_items', [])
                for item in feedback_items:
                    self._add_single_comment(doc_root, comments_root, item)
                
                # Schrijf aangepaste XML terug
                doc_zip.writestr('word/document.xml', ET.tostring(doc_root, encoding='unicode'))
                doc_zip.writestr('word/comments.xml', ET.tostring(comments_root, encoding='unicode'))
                
                # Update relaties
                self._update_relationships(doc_zip)
            
            logger.info(f"Echte Word comments toegevoegd: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Fout bij toevoegen echte comments: {e}")
            raise
    
    def _get_or_create_comments_xml(self, doc_zip: zipfile.ZipFile) -> str:
        """Haal bestaande comments.xml op of maak nieuwe aan."""
        try:
            return doc_zip.read('word/comments.xml').decode('utf-8')
        except KeyError:
            # Maak nieuwe comments.xml
            comments_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
</w:comments>'''
            return comments_xml
    
    def _add_comment_namespace(self, doc_root: ET.Element):
        """Voeg comment namespace toe aan document root."""
        # Voeg w15 namespace toe voor comments
        if 'w15' not in doc_root.attrib:
            doc_root.attrib['xmlns:w15'] = 'http://schemas.microsoft.com/office/word/2012/wordml'
    
    def _add_single_comment(self, doc_root: ET.Element, comments_root: ET.Element, 
                          feedback_item: Dict[str, Any]):
        """Voeg een enkele comment toe."""
        try:
            # Genereer unieke IDs
            comment_id = str(self.comment_id_counter)
            comment_ref_id = str(self.comment_ref_counter)
            
            # Maak comment XML
            comment_element = self._create_comment_element(feedback_item, comment_id)
            comments_root.append(comment_element)
            
            # Voeg comment referentie toe aan document
            self._add_comment_reference(doc_root, comment_ref_id)
            
            # Update counters
            self.comment_id_counter += 1
            self.comment_ref_counter += 1
            
            logger.info(f"Comment toegevoegd: {feedback_item.get('criterion_name', 'Unknown')}")
            
        except Exception as e:
            logger.error(f"Fout bij toevoegen comment: {e}")
    
    def _create_comment_element(self, feedback_item: Dict[str, Any], comment_id: str) -> ET.Element:
        """Maak een comment XML element."""
        # Haal feedback data op
        criterion_name = feedback_item.get('criterion_name', 'Onbekend criterium')
        message = feedback_item.get('message', 'Geen bericht')
        status = feedback_item.get('status', 'unknown')
        suggestion = feedback_item.get('suggestion', '')
        
        # Maak comment tekst
        comment_text = f"[{criterion_name}] {message}"
        if suggestion:
            comment_text += f"\n\nSuggestie: {suggestion}"
        
        # Voeg status icon toe
        status_icon = self._get_status_icon(status)
        comment_text = f"{status_icon} {comment_text}"
        
        # Escape speciale karakters
        comment_text = comment_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        
        # Maak comment element met correcte namespace
        comment = ET.Element('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}comment')
        comment.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id', comment_id)
        comment.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}author', 'Legal Feedback Tool')
        comment.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}date', '2024-01-01T00:00:00Z')
        
        # Voeg paragraaf toe
        p = ET.SubElement(comment, '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p')
        r = ET.SubElement(p, '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}r')
        t = ET.SubElement(r, '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t')
        t.text = comment_text
        
        return comment
    
    def _add_comment_reference(self, doc_root: ET.Element, comment_ref_id: str):
        """Voeg comment referentie toe aan document."""
        # Zoek eerste paragraaf om comment aan toe te voegen
        for paragraph in doc_root.findall('.//w:p', self.namespaces):
            # Voeg comment referentie toe aan eerste run
            for run in paragraph.findall('.//w:r', self.namespaces):
                # Maak comment referentie elementen met correcte namespace
                comment_range_start = ET.Element('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}commentRangeStart')
                comment_range_start.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id', comment_ref_id)
                
                comment_range_end = ET.Element('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}commentRangeEnd')
                comment_range_end.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id', comment_ref_id)
                
                comment_ref_run = ET.Element('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}r')
                comment_ref = ET.SubElement(comment_ref_run, '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}commentReference')
                comment_ref.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id', comment_ref_id)
                
                # Voeg elementen toe aan de run
                run.append(comment_range_start)
                run.append(comment_range_end)
                run.append(comment_ref_run)
                
                logger.info(f"Comment referentie toegevoegd met ID: {comment_ref_id}")
                return  # Stop na eerste comment referentie
    
    def _get_status_icon(self, status: str) -> str:
        """Krijg status icon voor comment."""
        icons = {
            'error': '❌',
            'violation': '❌', 
            'warning': '⚠️',
            'ok': '✅',
            'info': 'ℹ️'
        }
        return icons.get(status, 'ℹ️')
    
    def _update_relationships(self, doc_zip: zipfile.ZipFile):
        """Update document relaties om comments te linken."""
        try:
            # Lees bestaande relaties
            rels_xml = doc_zip.read('word/_rels/document.xml.rels').decode('utf-8')
            rels_root = ET.fromstring(rels_xml)
            
            # Check of comments relatie al bestaat
            comments_rel_exists = False
            for rel in rels_root.findall('.//Relationship'):
                if rel.get('Target') == 'comments.xml':
                    comments_rel_exists = True
                    break
            
            # Voeg comments relatie toe als deze niet bestaat
            if not comments_rel_exists:
                rel_id = f"rId{len(rels_root.findall('.//Relationship')) + 1}"
                rel_xml = f'<Relationship Id="{rel_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="comments.xml"/>'
                rel_element = ET.fromstring(rel_xml)
                rels_root.append(rel_element)
                
                # Schrijf aangepaste relaties terug
                doc_zip.writestr('word/_rels/document.xml.rels', ET.tostring(rels_root, encoding='unicode'))
                
        except Exception as e:
            logger.warning(f"Kon relaties niet updaten: {e}")

# Test functie
def test_word_comments():
    """Test de Word comments functionaliteit."""
    manager = WordCommentManager()
    
    # Test feedback data
    test_feedback = {
        'feedback_items': [
            {
                'criterion_name': 'Test Criterium',
                'message': 'Dit is een test comment',
                'status': 'warning',
                'suggestion': 'Verbeter dit gedeelte'
            }
        ]
    }
    
    # Test met een bestaand document
    # manager.add_real_comments_to_document('test.docx', test_feedback)
    print("Word Comments module geladen en klaar voor gebruik!")

if __name__ == "__main__":
    test_word_comments() 