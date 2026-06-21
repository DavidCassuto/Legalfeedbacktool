# Roadmap — meertalig & vorm-onafhankelijk maken

*Opgesteld met Claude (Opus 4.8) — 20 juni 2026*

Doel: de holistische feedbacktool laten schalen naar andere opleidingen en landen.
Twee sporen: **meertalig** (NL → EN → HE) en **vorm-onafhankelijke rubric-inname**
(elk opleidingsformulier, niet alleen het ene Nederlandse Excel).

Belangrijke uitgangspunten (beslist):
- Eén codebase met een **taalinstelling** (geen aparte forks).
- Opzet **algemener academisch** i.p.v. juridisch-specifiek.
- Standaard-criteria worden **per taal herschreven** (geen vertaling) en zijn
  per klant aanpasbaar.
- **Hebreeuws** wordt de derde taal → **RTL (rechts-naar-links)**. Daarom wordt
  richting (`ltr`/`rtl`) en locale vanaf het begin in het ontwerp meegenomen,
  zodat HE later "config + CSS-controle" is i.p.v. een herbouw.

---

## Fase 0 — Fundament (maakt NL+EN+HE mogelijk)
1. **Taal als instelling** — twee begrippen: *UI-taal* (wat de docent ziet) en
   *feedback-taal* (taal van het studentdocument, vastgelegd bij de rubric).
   Elke taal draagt: code (`nl`/`en`/`he`), richting (`ltr`/`rtl`), locale.
2. **Prompt taal-gestuurd** — expliciete instructie "geef alle feedback in {taal}";
   later de prompt-scaffolding taal-neutraal maken.
3. **Standaard-criteria in een taal-register** — `DEFAULT_*` per taal; per klant
   aanpasbaar via de rubric-config.
4. **UI-vertaallaag + RTL-bewuste CSS** — teksten uit templates naar een
   vertaalmechanisme; logische CSS-eigenschappen; `<html lang dir>` per taal.

## Fase 1 — Engels live
5. Engelse standaard-criteria **herschrijven** (Engelse grammatica/stijl, Engelse
   AI-tells, algemener-academisch).
6. Engelse UI-teksten.
7. Testen op een Engels document.

## Fase 2 — Vorm-onafhankelijke rubric-inname
8. Rubric-extractie: criteria uit **cellen** lezen naast tekstvakken.
9. Omgaan met formulieren **zonder varianten**; variantnamen afleiden uit de
   werkbladen i.p.v. vaste Nederlandse productnamen.
10. Beroepsproduct-/bijlage-herkenning configureerbaar/generiek maken.
11. Plak- en distilleer-routes blijven de universele vangnet-ingang.

## Fase 3 — Hebreeuws
12. Hebreeuwse criteria + UI-teksten.
13. RTL-CSS-audit + Word-output- en verbatim-citaat-testen (bidi, niqqud,
    bijlage-/inhoudsopgave-detectie).

---

**Prioriteit:** Fase 0 eerst (eenmalige investering). Daarna Fase 1 (Engels) en
Fase 2 (vorm-agnostisch) parallel of na elkaar. Hebreeuws als laatste, met de
UI-/Word-testronde.

**Status:** Fase 0 gestart op 20 juni 2026.
