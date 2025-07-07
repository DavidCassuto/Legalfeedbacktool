#!/usr/bin/env python3
"""
Test script voor AI feedback functionaliteit.
"""

import os
import sys
sys.path.append('src')

from ai_feedback import AIFeedbackGenerator
from word_export import WordFeedbackExporter

def test_ai_feedback():
    """Test de AI feedback functionaliteit."""
    print("🧪 Test AI Feedback Functionaliteit")
    print("=" * 50)
    
    # Check API key
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ GEMINI_API_KEY niet ingesteld")
        print("   Stel de API key in als environment variable:")
        print("   Windows: set GEMINI_API_KEY=jouw_api_key")
        print("   Linux/Mac: export GEMINI_API_KEY=jouw_api_key")
        return False
    
    print("✅ Gemini API key gevonden")
    
    try:
        # Test AI feedback generator
        print("\n🔧 Initialiseer AI feedback generator...")
        ai_generator = AIFeedbackGenerator(api_key=api_key)
        print("✅ AI feedback generator geïnitialiseerd")
        
        # Test sectie feedback
        print("\n📝 Test sectie feedback generatie...")
        test_section_content = """
        Inleiding
        
        Dit onderzoek richt zich op het analyseren van de effectiviteit van feedback tools 
        in academische contexten. De behoefte aan gestructureerde feedback is groot, 
        vooral in het hoger onderwijs waar studenten vaak behoefte hebben aan duidelijke 
        richtlijnen voor het verbeteren van hun werk.
        
        Het doel van dit onderzoek is om te bepalen hoe feedback tools kunnen bijdragen 
        aan de kwaliteit van academische documenten en de leerervaring van studenten.
        """
        
        feedback = ai_generator.generate_section_feedback(
            section_name="Inleiding",
            section_content=test_section_content,
            document_type="Academisch rapport"
        )
        
        print("✅ Sectie feedback gegenereerd")
        print(f"   Score: {feedback.get('overall_score', 'N/A')}/10")
        print(f"   Sterke punten: {len(feedback.get('strengths', []))}")
        print(f"   Verbeterpunten: {len(feedback.get('weaknesses', []))}")
        print(f"   Suggesties: {len(feedback.get('suggestions', []))}")
        
        # Test document overview
        print("\n📊 Test document overview...")
        sections_data = [feedback]
        document_feedback = ai_generator.generate_document_overview(sections_data)
        
        print("✅ Document overview gegenereerd")
        print(f"   Gemiddelde score: {document_feedback.get('average_score', 'N/A')}")
        print(f"   Algemene beoordeling: {document_feedback.get('overall_assessment', 'N/A')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Fout bij testen: {e}")
        return False

def test_word_export():
    """Test de Word export functionaliteit."""
    print("\n🧪 Test Word Export Functionaliteit")
    print("=" * 50)
    
    try:
        # Test Word export
        print("🔧 Initialiseer Word export...")
        exporter = WordFeedbackExporter()
        print("✅ Word export geïnitialiseerd")
        
        # Test feedback data structuur
        test_feedback_data = {
            'sections': [
                {
                    'name': 'Inleiding',
                    'found': True,
                    'feedback_items': [
                        {
                            'status': 'ok',
                            'message': 'Goede inleiding met duidelijke probleemstelling',
                            'suggestion': 'Voeg meer context toe'
                        }
                    ]
                }
            ],
            'ai_feedback': {
                'sections': [
                    {
                        'section_name': 'Inleiding',
                        'overall_score': 8,
                        'strengths': ['Duidelijke structuur', 'Goede probleemstelling'],
                        'weaknesses': ['Kan meer context gebruiken'],
                        'suggestions': ['Voeg meer achtergrondinformatie toe']
                    }
                ],
                'document': {
                    'average_score': 8.0,
                    'overall_assessment': 'Goed document met ruimte voor verbetering'
                }
            }
        }
        
        print("✅ Test feedback data structuur gemaakt")
        
        # Test samenvatting document maken
        print("📄 Test samenvatting document maken...")
        summary_path = "test_feedback_summary.docx"
        exporter.create_feedback_summary_document(
            feedback_data=test_feedback_data,
            output_file_path=summary_path
        )
        
        if os.path.exists(summary_path):
            print("✅ Samenvatting document gemaakt")
            os.remove(summary_path)  # Cleanup
            print("✅ Test bestand opgeruimd")
        else:
            print("❌ Samenvatting document niet gemaakt")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Fout bij Word export test: {e}")
        return False

def main():
    """Hoofdfunctie voor het testen."""
    print("🚀 Start Feedback Tool Tests")
    print("=" * 50)
    
    # Test AI feedback
    ai_success = test_ai_feedback()
    
    # Test Word export
    word_success = test_word_export()
    
    # Resultaat
    print("\n📊 Test Resultaten")
    print("=" * 50)
    print(f"AI Feedback: {'✅ Geslaagd' if ai_success else '❌ Gefaald'}")
    print(f"Word Export: {'✅ Geslaagd' if word_success else '❌ Gefaald'}")
    
    if ai_success and word_success:
        print("\n🎉 Alle tests geslaagd! De feedback tool is klaar voor gebruik.")
        print("\n📋 Volgende stappen:")
        print("1. Start de Flask applicatie: python src/main.py")
        print("2. Upload een Word document")
        print("3. Bekijk de AI feedback")
        print("4. Export naar Word met feedback")
    else:
        print("\n⚠️ Sommige tests zijn gefaald. Controleer de configuratie.")

if __name__ == "__main__":
    main() 