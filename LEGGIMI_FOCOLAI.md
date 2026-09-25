# Focolai attivi in Puglia (NASA FIRMS)

Pagina `focolai.html`: punti di calore rilevati dai satelliti NASA sul solo territorio pugliese.

## File da copiare nel repository del sito

```
focolai.html                    la pagina
data/firms_puglia.json          il file dei dati (all'inizio vuoto, lo riempie l'automazione)
scripts/fetch_firms.py          lo script che scarica i dati dalla NASA
scripts/puglia_comuni.json      i confini dei comuni pugliesi, per tenere solo i punti in Puglia
.github/workflows/firms.yml     l'automazione che esegue lo script ogni 30 minuti
```

La cartella `.github` inizia con un punto: su Mac e Linux è nascosta. Caricala comunque, altrimenti l'automazione non parte.

## Configurazione (una volta)

1. **Chiave FIRMS gratuita**: richiedila su https://firms.modaps.eosdis.nasa.gov/api/area/ (pulsante *Get MAP_KEY*). Arriva per email.
2. **Salvala nei Secrets del repository**: *Settings → Secrets and variables → Actions → New repository secret*,
   nome `FIRMS_MAP_KEY`, valore la chiave. Non scriverla mai nei file: il repository è pubblico.
3. **Permessi dell'automazione**: *Settings → Actions → General → Workflow permissions*, scegli *Read and write permissions*.
4. **Primo avvio**: scheda *Actions → Aggiorna focolai FIRMS → Run workflow*. Dopo un minuto `data/firms_puglia.json` si riempie.
   Da lì in poi parte da solo ogni 30 minuti.

## Come si usa la pagina

- `focolai.html` legge `data/firms_puglia.json` e si aggiorna da sola ogni 10 minuti.
- `focolai.html?demo=1` mostra **dati simulati**, con una striscia rossa ben visibile: serve solo per provare la pagina.
- *Aggiorna subito dai server NASA*: scarica i dati in quel momento con la chiave inserita nella pagina.
  Funziona solo se i server NASA permettono la lettura diretta dal browser (non verificato).

## Limiti da dichiarare

- **Tempo quasi reale, non reale**: il dato arriva di solito entro alcune ore dal passaggio del satellite,
  più fino a 30 minuti dell'automazione e fino a 10 minuti di cache di GitHub Pages.
- **Pochi passaggi al giorno**: i satelliti VIIRS e MODIS passano sulla Puglia solo alcune volte al giorno.
- **Un punto di calore non è sempre un incendio boschivo**: può essere una bruciatura agricola, un impianto industriale o un falso allarme.
- Le **aree industriali note** (Taranto, Brindisi Cerano) sono nascoste per impostazione predefinita.
  Posizioni e raggi sono approssimativi: si modificano in `focolai.html`, nella costante `AREE_INDUSTRIALI`.
- GitHub può ritardare le esecuzioni programmate e le sospende nei repository pubblici senza attività per 60 giorni.
