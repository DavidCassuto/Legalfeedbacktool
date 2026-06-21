# DocuCheck — Strategisch Rapport
*Opgesteld: Juni 2026 | Hermes Strategic Advisory*

---

## INHOUDSOPGAVE

1. [Waarom de tool goed genoeg is voor investering](#deel-1-waarom-de-tool-goed-genoeg-is)
2. [De vijf belangrijkste faalredenen en mitigaties](#deel-2-faalredenen-en-mitigaties)
3. [Concurrentieanalyse](#deel-3-concurrentieanalyse)
4. [Waar moet de €300K–400K seed aan worden besteed?](#deel-4-seed-budget)

---

# DEEL 1: WAAROM DE TOOL GOED GENOEG IS

## Het kernprobleem dat niemand anders oplost

Het probleem dat DocuCheck oplost is niet "studenten willen betere feedback." Het is:
**de scriptiedocent is al 40 jaar de bottleneck in scriptiekwaliteit, en dat is structureel nooit aangepakt.**

Een HBO-rechtenstudent krijgt gemiddeld 2–4 feedbackrondes over 6–12 maanden. Elke ronde kost een begeleider 3–6 uur leeswerk, annoteren en terugkoppelen. Een begeleider begeleid 10–20 studenten tegelijk. De math klopt niet — dus geven begeleiders oppervlakkige feedback. Dat was niet op te lossen vóór LLMs. Nu is het dat wel.

---

## Waarom dit GEEN ChatGPT-wrapper is

**1. Documentparsing met structuurbehoud**
Een student die 60 pagina's plakt in ChatGPT: context-window vol, opmaak weg, voetnoten verdwenen, geen ruimtelijke verwijzing. DocuCheck parset `.docx` met `python-docx`, behoudt koppen, alineanummers en positiemetadata. Feedback is *verankerd*: "alinea 3.2, paragraaf 4 adresseert het normatieve kader onvoldoende" — dat is bruikbaar. "Je methodologie is zwak" is dat niet.

**2. Rubric-mapping als structurele constraint**
ChatGPT geeft feedback op basis van wat het denkt dat "goede schrijfstijl" is. DocuCheck dwingt de AI om elk criterium uit de rubric — inclusief Nederlandse juridische begrippen als "functionele deelvraag," "methodologische verantwoording," "SMART-doelstelling" — te adresseren voor elk relevant stuk tekst. Dat is een fundamenteel andere output.

**3. Word-commentaren als workflow-integratie**
De output is een `.docx` met ingesloten `<w:comment>` XML-elementen, verankerd aan specifieke tekstfragmenten — precies zoals een begeleider het handmatig zou doen. Een begeleider opent het bestand, ziet de comments in de kantlijn, en kan er direct op reageren. Dat is een andere *categorie* van ervaring, geen marginale verbetering.

**4. De holistische analyse-engine**
De huidige prototype-versie vereist géén voorgedefinieerde secties. De AI leest het hele document en bepaalt zelf welke passages relevant zijn voor welk criterium. Dit goed laten werken op wisselende documentkwaliteit vereist weken aan prompt engineering. Dat kan een student niet reproduceren in een ChatGPT-sessie.

**5. Tijdwinst die telt**
- DIY-aanpak: kopiëren, prompt schrijven, wall-of-text interpreteren, handmatig correleren — **45–90 minuten**
- DocuCheck: upload, kies rubric, download — **5 minuten**

Dat is geen marginale tijdwinst. Dat is een ander product.

---

## Het platform dat hieronder zit

De kern-engine — Rubric + Document → Gestructureerde feedback in vertrouwd formaat — werkt voor *elk* domein met beoordelingscriteria:

| Domein | Betalingsbereidheid | Concurrentie nu |
|---|---|---|
| HBO/WO afstudeerstudenten (NL) | Middel | Laag |
| EU-subsidieaanvragen (Horizon Europe) | Hoog | Vrijwel nul |
| Juridische memo's bij advocatenkantoren | Zeer hoog | Medium |
| Corporate compliance documenten | Hoog | Medium |
| Medische casusverslagen | Hoog | Laag |

**Waarom juridisch Nederland het juiste startpunt is:**
- Gestandaardiseerde rubrics overdraagbaar tussen de 13 Nederlandse rechtenfaculteiten
- Homogene documentformaten (OSCOLA, vaste structuurconventies)
- Acute begeleiderspijn — goed gedocumenteerd in NL onderwijsliteratuur
- Slechts 13 primaire beslissers. Krijg je 3 instellingen, dan heb je geloofwaardige proof-of-concept

---

## Waarom nu, niet 3 jaar geleden

| Factor | Situatie 2022 | Situatie 2025 |
|---|---|---|
| LLM-kwaliteit | Generiek, begeleiders zouden het afwijzen | Claude 3/GPT-4 geeft professioneel geloofwaardige feedback |
| API-kosten | $2–8 per documentanalyse | €0,10–0,40 per analyse |
| Word-generatie | Specialistisch, pijnlijk | `python-docx` comment-XML is een opgelost engineeringprobleem |
| EU AI Act | Niet van kracht | Compliance-druk richting auditbare tools — tailwind voor institutionele verkoop |

---

## De verdedigbare positie die gebouwd KAN worden

Het Word-formaat alleen is geen moat. Maar dit is:

| Verdedigbare asset | Hoe het werkt |
|---|---|
| **Rubric-bibliotheek** | 200–500 gevalideerde Nederlandse rubrics per opleiding — dataset die jaren duurt om na te maken |
| **Begeleider-workflow integratie** | Begeleiders beheren rubrics *in* DocuCheck → tool wordt institutionele dependency |
| **Institutionele relaties** | Getekende DPA + LMS-integratie creëren switching costs los van productkwaliteit |
| **Uitkomstdata** | "Studenten die DocuCheck gebruikten leverden 23% sneller definitieve versie in" — sluit deals |
| **Domein-specifieke prompt engineering** | Kennis van NL juridische methodologie, HBO- vs. WO-conventies — niet triviaal na te bouwen |

---

## Wat een investeerder verwacht na 18 maanden

| KPI | Minimumdrempel | Sterk geval |
|---|---|---|
| Betalende instellingen | 2 getekende contracten | 4–5 |
| ARR | €60.000 | €150.000–200.000 |
| Studentgebruikers (gratis + betaald) | 1.500 | 4.000+ |
| Pilot-naar-betaald conversie | >40% | >60% |
| Tweede discipline gelanceerd | Ja | 2 extra disciplines |
| Gross Margin | >65% | >75% |

> **Eerlijk: €100K ARR in 18 maanden is de ondergrens van levensvatbaarheid, niet een doel om te vieren.** Met een team van 2–3 moet je €200–250K targeten.

---

# DEEL 2: FAALREDENEN EN MITIGATIES

## Faalreden 1: GDPR / Universitaire inkoopwal

**Waarom het echt gevaarlijk is:**
Elke tool die studentgegevens verwerkt vereist een DPA én DPIA. Anthropic is Amerikaans — data naar hun API sturen is grensoverschrijdende doorgifte onder GDPR. Eén DPO die "nee" zegt, en het gesprek is voorbij. Eén tweet van een privacybewuste professor kan een pilot stoppen.

**Concrete mitigatiestappen:**

| Tijdlijn | Actie | Kosten |
|---|---|---|
| Week 1–2 | Anthropic's commerciële DPA/SCC-pakket opvragen | Gratis |
| Maand 1–2 | DPIA-template laten opstellen door privacyconsultant | €2.000–4.000 |
| Maand 2–3 | Standaard verwerkersovereenkomst opstellen | €1.000–2.000 |
| Maand 3–4 | EU-data residency optie (Azure OpenAI EU-regio) | €500–1.000 |
| Doorlopend | DPO bij doelinstelling identificeren VOOR procurement | Tijd |

**Wat succes eruitziet:** Eerste DPA getekend. DPIA goedgekeurd door een universitaire DPO.

**Residueel risico:** 20–30% kans dat 1–2 instellingen onbereikbaar zijn door AI-moratoriums. Spreid targets over meerdere instellingen.

---

## Faalreden 2: Microsoft Copilot maakt DocuCheck overbodig

**Copilot vandaag:**
- ✅ Algemene schrijfsugesties, samenvatting, hertekst
- ❌ Kan géén rubric als beoordelingsinput accepteren
- ❌ Plaatst géén inline kantlijncomments verankerd aan rubriccriteria
- ❌ Geeft géén downloadbaar Word-bestand met kant-en-klare comments terug
- ❌ SURF-deployment varieert sterk — niet elke student heeft het

**Copilot in 12–18 maanden:** Waarschijnlijk rubric-intake, comment-anchoring, batch-verwerking. Microsoft beweegt richting "task-complete."

**Concrete differentiatie die overleeft:**

1. **Rubric-bibliotheek** — Copilot kent de HBO-Rechten rubric van Avans niet. DocuCheck wel.
2. **Begeleiderslaag** — Supervisordashboard: begeleider keurt AI-feedback goed vóór levering aan student
3. **Cohortanalytics** — "78 van 200 studenten faalden op criterium 3.2" — dat is een faculteitsbeheertool
4. **Audit trail voor AI Act compliance** — Gedocumenteerde, tijdgestempelde feedback per student

**De ene feature die het competitive window het meest verlengt:**
**Institutional Rubric Locking + Faculty Co-authorship Portal** — begeleiders bouwen en beheren hun officiële rubric *in* DocuCheck. De rubric zit nu *in* de tool. Verhuizen naar concurrent = rubric opnieuw opbouwen + aanbesteding opstarten. Dat is een echte switching cost.

---

## Faalreden 3: TAM te klein als je bij rechten blijft

**Het juiste expansieschema:**

| Periode | Actie | Marktgrootte |
|---|---|---|
| Jaar 1 | NL rechten — product-market fit | ~5.000 studenten/jaar |
| Jaar 1–2 | Alle HBO/WO disciplines NL | ~50.000 studenten/jaar |
| Jaar 2 | Vlaanderen | +20% van NL markt |
| Jaar 2 | EU-subsidieaanvragen (Horizon Europe) | Hoge betalingsbereidheid, nul concurrentie |
| Jaar 2–3 | Duitstalig (Hausarbeit, Seminararbeit) | 300.000+ rechtenstudenten |
| Jaar 3+ | Law firms, corporate compliance | Hoge ACV, andere sales motion |

**Hoe rubric-pakketten efficiënt bouwen:**
Partner met 1–2 coördinatoren per discipline in ruil voor gratis toegang of co-auteursvermeldng. Per pack: 15–20 uur faculteitstijd + 10–15 uur engineering.

---

## Faalreden 4: Solo-founder bandbreedte

**Minimaal levensvatbaar team:**

| Rol | Tijdlijn | Kosten |
|---|---|---|
| Commercieel co-founder / sales lead | Maand 1–3 | €55.000–75.000/jaar of equity |
| Privacy/compliance consultant (fractioneel) | Maand 1–6 | €1.500–2.500/maand |
| Junior sales/customer success | Maand 12+ (indien ARR dit rechtvaardigt) | €30.000–35.000/jaar |

**Waar je een co-founder vindt:**
- SURF-community events en werkgroepen
- YES!Delft, Utrecht Inc, Rockstart
- LinkedIn: "innovation coordinator" bij NL universiteiten

**Stop direct met:**
- Features bouwen die geen instelling heeft gevraagd
- Generieke startup-evenementen bijwonen
- Je eigen boekhouding doen

---

## Faalreden 5: Pricing-val

**De prijsarchitectuur:**

| Tier | Prijs | Inhoud | Doel |
|---|---|---|---|
| **Gratis** | €0 | 2 analyses lifetime, publieke rubrics, watermark | Studentadoptie, institutionele bewustwording |
| **Student Pro** | €12–18/maand of €8–12/analyse | Onbeperkt, instituutsrubrics, ongemerkt | Studenten wiens instelling nog niet gecontracteerd is |
| **Institutioneel** | €3.000–8.000/jaar per faculteit | Onbeperkt + supervisordashboard + cohortanalytics + DPA-pakket | Onder aanbestedingsdrempel (~€5.000–10.000) |

**Pilot-naar-betaald aanpak:**
Pilotcontract bevat: (a) DPA al getekend, (b) heldere conversietermijn in het contract, (c) commitment tot referentie-case.

---

# DEEL 3: CONCURRENTIEANALYSE

## Positioneringsmatrix

```
                    RUBRIC-SPECIFIEKE FEEDBACK
                              ▲
                              │
                   DocuCheck ●│  ← Jouw unieke terrein
                              │
STUDENT-FACING ◄──────────────┼──────────────► BEGELEIDER-FACING
                              │
     ChatGPT/Claude DIY ●     │     Turnitin Feedback Studio ●
                              │
     Scribbr ●                │
     (taal, niet inhoud)      │
                              ▼
                      GENERIEKE FEEDBACK

  Microsoft Copilot (nu):      generiek / student-facing
  Microsoft Copilot (18 mnd):  beweegt naar jouw kwadrant ← gevaar
```

---

## Concurrent 1: Microsoft Copilot in Word
**Kill probability: Medium | Timeline: 18–30 maanden**

**Kan vandaag niet:**
- Rubric als beoordelingsinput accepteren
- Inline kantlijncomments anchored aan rubriccriteria plaatsen
- Downloadbaar Word-bestand genereren (output gaat naar sidebar)

**DocuCheck's voordeel nu:** Werkt vandaag, 5 minuten, verankerde kantlijncomments, law-specifieke rubrics.

**Wat je moet bouwen:** Supervisordashboard, LMS-integratie, audit trail voor AI Act — dingen die Microsoft niet voor niches bouwt.

---

## Concurrent 2: ChatGPT/Claude direct
**Kill probability: Laag | Timeline: Meteen en doorlopend**

Een goed-promptende student haalt indrukwekkende resultaten. Maar: geen Word-output, geen comment-ankering, 45–90 minuten werk vs. 5 minuten, inconsistente rubric-coverage. **De dreiging is een vloer, geen plafond.**

---

## Concurrent 3: Scribbr
**Kill probability: Laag (direct) / Medium (M&A)**

Scribbr doet vandaag géén rubric-gebaseerde feedback. Hun editors zijn taalredacteuren. Menselijke redactie: €300–500/document vs. €10–20 bij DocuCheck.

**Meest interessante speler:** Scribbr heeft het merk, de studentrelaties, de betalingsinfrastructuur. Een white-label deal of acquisitie is plausibel en waardevoller dan een concurrentieoorlog. **Scribbr is je meest waarschijnlijke acquirer.**

---

## Concurrent 4: Turnitin / Feedback Studio
**Kill probability: Medium-High | Timeline: 18–36 maanden**

Turnitin zit al bij vrijwel elke Nederlandse universiteit. Feedback Studio is een beoordelaarstool (instructeur-kant), niet student-kant. AI-feedback pilot loopt — maar generiek, niet rubric-specifiek.

**De gevaarlijkste concurrent** — niet omdat de student kiest, maar omdat de instelling simpelweg een feature aanzet. Geen student maakt ooit een keuze; de switch gebeurt boven hun hoofd.

**DocuCheck's enige verdediging:** Institutionele contracten tekenen *vóórdat* Turnitin hun feature shipt. Canvas LTI-integratie overwegen.

---

## Concurrent 5: De zelf-bouwende professor
**Kill probability: Laag**

Een technisch vaardige professor kan een weekend-prototype bouwen. Maar maintenance kost FTE-equivalent, GDPR-compliance kost maanden institutionele juridische review, schaal werkt niet.

**Build vs. Buy voor een instelling:**

| Factor | Bouwen | Kopen (DocuCheck) |
|---|---|---|
| Deployment | 4–8 weken | Dezelfde dag |
| GDPR-compliance | 6–12 weken juridisch werk | Pre-gecertificeerd |
| Onderhoud | Doorlopend (1+ FTE) | Inbegrepen |
| Aansprakelijkheid | Persoonlijk/onduidelijk | Contractueel |

**Remedie:** Institutionele contracten vroeg sluiten vóórdat een faculteitsprototype informele standaard wordt.

---

## Samenvattende dreigingstabel

| Concurrent | Kill Probability | Timeline | Primaire dreiging |
|---|---|---|---|
| Microsoft Copilot | **Medium** | 18–30 maanden | SURF-deployment + rubric feature |
| ChatGPT/Claude DIY | **Laag** | Nu | UX-pariteit, student-sophisticatie |
| Scribbr | **Laag** (direct) / **Medium** (M&A) | 12–24 maanden | Acquisitie of nieuwe AI-product |
| Turnitin | **Medium-High** | 18–36 maanden | Institutionele LMS-feature |
| Faculteit DIY | **Laag** | Nu | Prototype-adoptie vóór contract |

---

# DEEL 4: SEED BUDGET

## Waar moet de €300K–400K aan worden besteed?

### Budget breakdown (gebaseerd op €350K midpoint)

| Categorie | Bedrag | % | Toelichting |
|---|---|---|---|
| 🧑‍💼 **Team & Hiring** | **€168.000** | **48%** | Grootste en meest kritische categorie |
| 📣 **Marketing & Sales** | **€42.000** | **12%** | Outreach, content, paid acquisition tests |
| 🛡️ **Runway Buffer** | **€42.000** | **12%** | 3–4 maanden operating reserve — niet aanraken |
| 🏛️ **GDPR & Compliance** | **€28.000** | **8%** | DPO, ISO 27001 prep, juridische templates |
| 🖥️ **Infrastructuur & Tech** | **€21.000** | **6%** | Cloud migratie, API-kosten, monitoring |
| 🔧 **Operationeel** | **€14.000** | **4%** | CRM, accountancy, coworking, contingency |
| **Totaal** | **€315.000** | | Resterende €35K–85K = uitbreiding runway of extra hiring |

---

### Team breakdown (de grootste post)

| Rol | Kosten | Timing |
|---|---|---|
| Head of Growth / Commercial Lead | €112.500 (18 mnd) | **Maand 1 — meest kritische hire** |
| Fractioneel GDPR/Legal Counsel | €18.000 (18 mnd) | Maand 1–2 |
| Part-time Product Designer/UX | €15.000 (6 mnd contract) | Maand 2–4 |
| Founder Salaris | €22.500 (€1.250/mnd) | Doorlopend |

---

### Gefaseerde uitgaven

**Maand 1–6: Fundament (€130.000)**
- Commercial Lead direct aannemen — elke week zonder is een week verloren outreach
- GDPR-counsel en DPO inschakelen voor maand 2
- Infrastructuur migreren van SQLite naar PostgreSQL vóór maand 3 (hard deadline voor institutionele demo's)
- 3–5 institutionele pilots tekenen (gratis of gereduceerd)
- Doel: GDPR-documentatie klaar voor procurement review

**Maand 7–12: Tractie (€110.000)**
- Pilots omzetten naar betalende contracten
- TAM-expansie: Belgische rechtenfaculteiten, MBA-programma's
- Content/SEO-programma starten
- Security audit commissionen (maand 8–9)
- Doel: €15.000–40.000 ARR, 2–3 betalende instellingen

**Maand 13–18: Schalen & Series A prep (€75.000)**
- Verdubbelen op wat werkt
- 1–2 aangrenzende verticalen (medische school, engineering theses)
- Series A investor outreach starten bij maand 14–15
- Doel: €80.000–150.000 ARR, 12+ institutionele klanten

---

### Wat je NIET moet uitgeven

- ❌ Duur kantoor — remote-first is normaal en geaccepteerd in NL
- ❌ Full agency rebrand — één goede UX-contractor > tien branding agencies
- ❌ Enterprise sales tools vóór je enterprise sales hebt (Salesforce etc. — HubSpot gratis tier is genoeg)
- ❌ Extra developers aannemen — jij bent de developer; leverage zit op de commercial kant
- ❌ Conferentie-sponsorships — bijwonen: €500; sponsoren: €10.000+
- ❌ Outsourced cold outreach agencies — spam naar NL onderwijsprocurement is permanente blacklisting

---

### De belangrijkste investering van allemaal

**Commercial Lead aannemen in Maand 1.**

Alles else — GDPR, marketing, infrastructuur — is noodzakelijk maar niet voldoende. De bottleneck is niet het product; het is distributie in een complex, langzaam institutioneel markt waar relaties en procurement-navigatie alles bepalen.

Als deze hire fout gaat — te junior, verkeerd netwerk, geen edtech B2B-ervaring — valt het hele 18-maanden plan in duigen. Besteed extra tijd aan deze hire. Bied equity boven een junior cash salaris als dat nodig is om iemand senior aan te trekken.

---

### Wanneer raakt het seed-geld op?

**Runway math:**
- Burn: ~€17.500–19.500/maand
- Runway zonder omzet: ~18–19 maanden
- Bij €100K ARR (€8.333/mnd inkomsten): effectieve netto-burn daalt naar ~€10.000–11.000/mnd → +3–4 maanden extra

**Wanneer Series A starten:**
- Begin investor gesprekken bij **€50.000–70.000 ARR** met bewijs dat institutionele contracten tekenen en uitbreiden
- Sluit Series A vóór je runway onder 6 maanden zakt
- Target close: bij **€100.000–120.000 ARR**

**Het Series A-verhaal (target: €1,5M–2,5M):**
> *"DocuCheck startte als AI-feedbacktool voor Nederlandse rechtenstudenten. In 18 maanden tekenden we contracten met [X] universiteiten, bereikten [X]K ARR, en ontdekten dat ons product even goed werkt voor medische, engineering en business scripties — elk programma met gestructureerde beoordelingscriteria. Europa heeft 4.000+ HEI's. We hebben bewezen dat institutionele procurement te kraken is in Nederland. Nu nemen we het playbook naar Duitsland, België en het VK."*

---

## CONCLUSIE: IS DE TOOL KLAAR VOOR INVESTERING?

**Conditioneel ja** — met drie niet-onderhandelbare uitvoeringsverplichtingen in jaar één:

1. ✅ **Eén DPA getekend** met één Nederlandse universiteit binnen 9 maanden
2. ✅ **500+ actieve studentgebruikers** via die instelling
3. ✅ **Commerciële partner** (co-founder of sales hire) aan boord vóór maand 6

De tool heeft echte productinzichten, echte technische differentiatie, en de timing is goed. Het concurrentievenster is **12–18 maanden breed**. De keuze is nu: gebruik die tijd om institutionele diepte te bouwen, of kijk toe hoe Microsoft en Turnitin het venster sluiten.

**Investment verdict: €300.000–400.000 seed, met milestones aan eerste institutioneel contract binnen 9 maanden en tweede discipline binnen 12 maanden.**

---

*DocuCheck Strategic Report — Hermes Strategic Advisory | Juni 2026*
*Vertrouwelijk — intern gebruik*
