# Kryptominer Kontrollpanel (PyQt5)

## 📖 Exakt vad programmet gör
Det här Python-skriptet är ett **grafiskt användargränssnitt (GUI)** byggt med **PyQt5**.  
Det fungerar som en central kontrollpanel för att hantera och automatisera olika kryptomining-program (s.k. *miners*).

---

## 🚀 Huvudfunktioner
- **Stöd för flera miners**  
  Konfigurera och kör fyra populära mining-program:
  - GMiner  
  - lolMiner  
  - T-Rex  
  - XMRig  

- **Automatisk styrning baserat på elpris**  
  - Hämtar elprisdata i realtid från [elprisetjustnu.se](https://elprisetjustnu.se)  
  - Stöd för svenska elområden **SE1–SE4**  
  - Startar miner om priset < tröskel (SEK/kWh)  
  - Stoppar miner om priset > tröskel  

- **Grafiskt gränssnitt**  
  - Flikar för att växla mellan miners  
  - Ange sökvägar till mining-programmen  
  - Konfigurera inställningar (algoritm, pool, användarnamn, lösenord, överklockning m.m.)  
  - Förifylld lista med NiceHash-pooler + möjlighet att ange egna  

- **Manuell kontroll**  
  - Starta/stoppa miners när som helst med knappar  

- **Loggning och övervakning**  
  - Realtidsloggar från miner och kontrollpanelen  

- **Anpassning och inställningar**  
  - Alla inställningar sparas mellan sessioner  
  - Flera teman: *Mörkt, Ljust, Nord, Matrix*  

---

## 📝 Sammanfattning
> Ett grafiskt program för att styra kryptovaluta-miners (GMiner, lolMiner, m.fl.).  
> Det kan automatiskt starta/stoppa mining baserat på aktuella svenska elpriser för att spara pengar.  
> Alla inställningar för varje miner kan konfigureras i gränssnittet.  
> Stöder även manuell kontroll, teman och loggning.

---

## 📦 Beroenden
För att köra skriptet måste följande vara installerat:

### Python-bibliotek
Installera via `pip`:
```bash
pip install PyQt5
pip install requests
pip install pytz

Externa program

Det här skriptet är en kontrollpanel och innehåller inte själva mining-programmen.
Du behöver själv ladda ner och installera de miners du vill använda (t.ex. GMiner, lolMiner, T-Rex, XMRig) och ange deras sökvägar i programmet.
du kan ställa in sökvägen till dom i programmet.
