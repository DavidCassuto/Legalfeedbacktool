# DocuCheck — feedbacktool voor scripties

*Een hulpmiddel dat studenten helpt beter te leren schrijven, door uitgebreide,
opbouwende feedback te geven waar begeleiders vaak de tijd niet voor hebben.*

---

## Waarom deze tool bestaat

Goede feedback op een scriptie kost veel tijd. Een begeleider moet eigenlijk
hoofdstuk voor hoofdstuk meelezen, taalfouten aanstrepen, letten op de juridische
schrijfstijl, controleren of de deelvragen écht beantwoord worden, en dat alles
ook nog netjes uitleggen. In de praktijk is daar te weinig tijd voor, zeker als
een begeleider meerdere studenten tegelijk heeft.

Het gevolg: studenten krijgen te weinig of te late feedback om er nog van te leren.

**DocuCheck neemt het tijdrovende leeswerk over** en geeft de student gerichte,
opbouwende feedback in het document zelf — zodat de begeleider zich kan richten op
de grote lijn en het persoonlijke gesprek.

---

## Wat het wél en niet is

- ✅ Het is een **educatieve schrijf-assistent**: hij legt uit wát beter kan en
  waaróm, zodat de student het leert.
- ❌ Het is **geen beoordelaar**: de tool geeft **geen cijfer**. Beoordelen blijft
  mensenwerk. De tool levert alleen de feedback die helpt om het werk te verbeteren.

Het bijzondere: de tool gebruikt de **feedback-aanpak van de opleiding zelf**. De
school bepaalt waar op gelet wordt en in welke toon — de tool schaalt die expertise
op naar elke student.

---

## Hoe het werkt (voor de gebruiker)

**Eenmalig instellen (door de opleiding):**
1. Upload het bestaande Excel-beoordelingsformulier in de **rubric-bibliotheek**.
   De tool haalt daar automatisch de criteria per beroepsproduct uit.
2. Vul (of pas aan) de **feedback-instellingen**: taalfouten, juridische
   schrijfkwaliteit, AI-stijldetectie, de toon van de feedback en extra
   inhoudelijke aandachtspunten. Er staan kant-en-klare standaarden klaar.

**Per scriptie (door docent of student):**
1. Upload het **Word-document** (.docx) van de student.
2. Kies de opgeslagen rubric en het beroepsproduct (of laat de tool dat zelf
   herkennen).
3. Bekijk de **kostenschatting** en klik op *Analyseren*.
4. Download het **Word-document met feedback** erin.

In dat document staat:
- **Opmerkingen (comments)** bij de juiste zin of alinea — over de inhoud per
  hoofdstuk, de schrijfkwaliteit en mogelijke AI-stijl.
- **Gele markeringen** bij taalfouten (spelling/grammatica), zonder opmerking —
  een lichte hint die de student zelf oplost.

---

## Welke feedback de tool geeft

1. **Inhoud per onderdeel** — volgt de rubric van de opleiding. Let o.a. op of de
   resultatenhoofdstukken hun deelvragen beantwoorden en of de deelvragen
   onderling en t.o.v. de hoofdvraag onderscheidend genoeg zijn.
2. **Taalfouten** — spelling, grammatica, interpunctie (gele markering).
3. **Juridische schrijfkwaliteit** — zinslengte, wollig taalgebruik, alinea-opbouw,
   bronvermelding enz. (als opmerking).
4. **AI-stijldetectie** — patronen die wijzen op AI-gegenereerde tekst.
5. **Toon van de feedback** — bemoedigend en begrijpelijk; de school stelt dit in.
   Suggesties (de oplossingsrichting) kunnen aan of uit.

---

## Slim en zuinig

- **Bijlagen worden overgeslagen**, maar het **beroepsproduct** (advies, ontwerp,
  implementatieplan) wordt er wel uitgevist en beoordeeld.
- Het **hele document gaat in één keer** door de tool, zodat samenhang tussen
  hoofdstukken meeweegt (bv. resultaten t.o.v. de deelvragen) — zonder extra kosten.
- Een instelbare **limiet** voorkomt een overdaad aan opmerkingen.

---

## Specificaties (eenvoudig)

- **Invoer:** Word-document (.docx) + Excel-beoordelingsformulier (.xlsx).
- **Uitvoer:** hetzelfde Word-document, met opmerkingen en markeringen erin.
- **Beroepsproducten:** PvA, Analyse, Advies, Ontwerp, Fabricaat, Eindgesprek.
- **Vorm:** webapplicatie met inlog; een rubric-bibliotheek per opleiding.
- **Techniek (op de achtergrond):** geavanceerde AI van Anthropic (Claude).
- **Doelgroep nu:** HBO-Rechten afstudeerscripties.

---

## Wat er nog te doen is

*Eerlijk overzicht van de huidige beperkingen en wensen — dit is nu een werkend
prototype, nog geen afgerond product.*

- **Plaatsing van opmerkingen** klopt meestal, maar niet altijd: opmerkingen die
  niet exact aan een tekstfragment te koppelen zijn, komen (bewust) in een aparte
  lijst i.p.v. op een verkeerde plek. Dit kan scherper.
- **Tabellen en figuren** worden nu niet "gezien" door de tool; feedback daarover
  (bv. "tabel zonder inleidende tekst") is daardoor onbetrouwbaar.
- **Eén limiet voor alle categorieën** — nog geen apart maximum per soort feedback
  (bv. taal hoog, AI laag).
- **Feedback over hoofdstuktitels** is lastig precies te plaatsen.
- **Alleen .docx** — gescande PDF's worden niet ondersteund (daar kan geen
  Word-opmerking in).
- **Echte praktijktest en fijnafstemming** van de feedbackkwaliteit op meer
  scripties is nog nodig.
- **Productierijp maken:** beheer per school/organisatie, gebruikersbeheer,
  kosten-/verbruiksbeheer, en bredere inzet buiten HBO-Rechten.
- **Kosten** lopen via een AI-tegoed; verbruik per school inzichtelijk maken is een
  wens.

---

*Status: prototype in ontwikkeling. Doel: een betrouwbare, betaalbare feedbacktool
die de schrijfbegeleiding van opleidingen opschaalt — zonder de docent te vervangen.*
