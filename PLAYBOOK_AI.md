# Playbook AI

## Modelul folosit
- Claude Sonnet 4.6

## Prompturi / replici
- Prompt 1: "Pagină de referință: https://www.opti.ro/ai-2026/ghid-recomandari-upsell/cookbook-cod-recomandari-ai Obiectiv Livrarea unui script care generează HTML-ul pentru conținutul paginii pe baza unei baze de date structurate. Scop (ce se generează) Se generează doar conținutul din containerul: main.article-content.opti-container-md.guide-content Se exclud explicit: ● meniu / navigație ● header/footer ● layout/cadru vizual general ● <head>, schema markup etc. 
Cerințe de output HTML-ul generat trebuie să păstreze, pe cât posibil, structura logică a paginii originale: ● paragrafe ● heading-uri și ierarhia lor (H2/H3/H4 etc.) ● liste și numerotări ● casete / calout-uri (tipuri diferite) ● ierarhia conținutului (secțiuni/subsecțiuni) Notă: Nu este obligatoriu să reproduceți exact clasele CSS existente, dar structura elementelor (tipurile de blocuri și ordinea lor) trebuie să fie consistentă cu HTML-ul afișat. Cerințe pentru baza de date Baza de date trebuie să fie structurată astfel încât să permită regenerarea conținutului (ex: pagină → secțiuni → blocuri → elemente)

Eu ma gandeam la structura asta: Scraper ia datele , initializeaza database-ul , si in rest un fisier .sql cu structura si altul .py care genereaza 

Uite ce e in main.article:"
- Prompt 2: "In loc sa cautam elementele dupa continut sau pozite , itereaza prin toti copii si vezi in ce structura sunt , de exemplu in loc de asta : article.find("p", string=lambda t: "Vei trece pas cu pas" in t)
mai bine facem if(tag_name==p) ... "

## Pași manuali între rulări
- Rularea 1: am observat ca agentul a facut totul hardcodat si am incercat sa minimizez cat de mult acest lucru
- Rularea 2: am modificat promptul pentru claritate
