# DocuCheck — Automatische Feedbacktool voor Studentendocumenten

## Wat is DocuCheck?

DocuCheck is een webgebaseerde feedbacktool waarmee docenten en onderwijsinstellingen automatisch
gestructureerde feedback geven op studentendocumenten. De tool analyseert een geüpload Word- of
tekstdocument aan de hand van volledig configureerbare beoordelingscriteria en geeft per sectie
concrete, bruikbare feedback terug.

De tool is ontwikkeld voor het Nederlandse hoger onderwijs en ondersteunt documenten zoals Plan van
Aanpak, onderzoeksrapporten, adviesdocumenten en andere gestructureerde werkstukken.

---

## Kernfunctionaliteit

### 1. Documentanalyse
- Upload een `.docx` of `.txt` bestand
- Automatische herkenning van secties op basis van kopstructuur (Heading-stijlen in Word)
- Fuzzy matching: secties worden herkend zelfs als studenten de koptekst iets anders formuleren
- Visuele weergave van gevonden en ontbrekende secties, inclusief woordtelling en betrouwbaarheidsscore

### 2. Configureerbare Beoordelingscriteria
Docenten stellen zelf in welke regels gelden. Beschikbare criteriumtypen:

| Type | Wat het doet |
|------|-------------|
| **Verboden woorden** | Detecteert ongewenst woordgebruik (bijv. "ik", "wij", "eigenlijk") |
| **Verplichte woorden** | Controleert of vaktermen of sleutelwoorden aanwezig zijn |
| **Woordtelling sectie** | Minumum/maximum aantal woorden per sectie |
| **Woordtelling alinea** | Minimum/maximum aantal woorden per individuele alinea |
| **AI-beoordeling** | Diepgaande inhoudsanalyse via Claude (Anthropic) of Gemini |
| **Stijl & formulering** | Detectie van AI-gegenereerde tekst, generieke formuleringen, gebrek aan eigen standpunt |
| **Structuurcontrole** | Aanwezigheid van deelvragen, alineastructuur, koppenstructuur |
| **Tekstuele criteria** | Vrij configureerbare inhoudelijke regels |

Elk criterium is koppelbaar aan specifieke secties, heeft een ernst-niveau (overtreding / waarschuwing /
info) en een kleurcodering voor de feedbackweergave.

### 3. Feedbackrapportage
- Overzichtelijk dashboard met tellingen: overtredingen, waarschuwingen, informatief, correct
- Feedback gegroepeerd per sectie, met exacte verwijzing naar de locatie in het document
- Concrete suggesties voor verbetering bij elke bevinding
- Exporteerbaar naar een Word-document met ingebouwde commentaren

### 4. Documenttypebeheer
- Meerdere documenttypen configureerbaar (bijv. Plan van Aanpak, Onderzoeksrapport, Adviesrapport)
- Per documenttype: eigen sectielijst, eigen criteriaset
- Eenvoudig uitbreidbaar zonder programmeerkennis

### 5. Meerdere gebruikers en organisaties
- Inlogfunctionaliteit met rollen (beheerder / docent)
- Ondersteuning voor meerdere organisaties (multi-tenancy)
- Gebruikersbeheer via de beheerdersinteface

### 6. AI-integratie
- Koppeling met **Anthropic Claude** voor kwalitatieve inhoudsbeoordeling
- Koppeling met **Google Gemini** als alternatief of aanvulling
- AI-stijldetectie: de tool herkent kenmerken van AI-gegenereerde tekst (overmatige opsommingen,
  generieke openingszinnen, symmetrische alineastructuur, ontbreken van eigen standpunt)
- AI-feedback is per criterium in- of uitschakelbaar

---

## Technische Specificaties

| Onderdeel | Details |
|-----------|---------|
| **Platform** | Web (browser-based), lokaal of server-hosted |
| **Backend** | Python 3.11 / Flask |
| **Database** | SQLite (eenvoudig te migreren naar PostgreSQL) |
| **Documentondersteuning** | `.docx` (Microsoft Word), `.txt` |
| **AI-providers** | Anthropic Claude, Google Gemini |
| **Installatie** | Python virtual environment, geen externe diensten vereist behalve API-sleutels |
| **Besturingssysteem** | Windows, macOS, Linux |

---

## Wat maakt DocuCheck onderscheidend?

- **Geen black box**: elk stuk feedback is traceerbaar tot een specifiek criterium en een specifieke
  locatie in het document
- **Volledig configureerbaar**: docenten beheren zelf criteria, secties en documenttypen via de
  webinterface — geen programmeertechnische kennis nodig
- **Schaalbaar**: van één docent tot meerdere organisaties met eigen documenttypen en criteria
- **AI als assistent, niet als vervanging**: de AI-beoordeling ondersteunt de docent, de criteria
  blijven in menselijke handen
- **Alinea-niveau analyse**: de tool beoordeelt niet alleen de sectie als geheel, maar ook elke
  individuele alinea — zodat studenten precies zien welk tekstblok aandacht verdient

---

## Typische Gebruikssituaties

1. **Formatieve feedback** tijdens schrijfproces — student uploadt concept, krijgt direct inzicht
2. **Summatieve ondersteuning** — docent gebruikt de analyse als startpunt voor eindbeoordeling
3. **Schriftelijke vaardigheidstoetsing** — gestandaardiseerde beoordeling over meerdere klassen
4. **Anti-plagiaat aanvulling** — AI-stijldetectie als indicator voor AI-gegenereerde content

---

## Status

De tool is functioneel en in gebruik. Actief in ontwikkeling. Criteria en documenttypen voor
Plan van Aanpak zijn geconfigureerd en getest. De export naar Word met feedbackcommentaren is
operationeel.

---

*DocuCheck — ontwikkeld voor het Nederlandse hoger onderwijs*
