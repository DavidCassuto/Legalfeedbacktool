# Server Management - Optimale Werkwijze

## 🚀 Snelle Start (Aanbevolen)

### Stap 1: Activeer de virtuele omgeving
```powershell
.\venv_lokaal\Scripts\Activate.ps1
```

### Stap 2: Start de server
```powershell
# Voor debug mode (aanbevolen voor ontwikkeling)
.\start_server_simple.ps1 -Debug

# Voor productie mode
.\start_server_simple.ps1
```

## 🔧 Alternatieve Methoden

### Methode 1: Handmatige activatie + directe start
```powershell
# 1. Activeer venv
.\venv_lokaal\Scripts\Activate.ps1

# 2. Start server direct
python src\main.py
```

### Methode 2: Gebruik het activatie script
```powershell
# 1. Activeer venv
.\activate_venv.ps1

# 2. Start server
python src\main.py
```

## ❌ Wat NIET te doen

- **Niet**: `.\start_server.ps1` gebruiken zonder eerst de venv te activeren
- **Niet**: `python src\main.py` uitvoeren zonder geactiveerde venv
- **Niet**: PowerShell sessie herstarten zonder venv opnieuw te activeren

## 🔍 Probleemdiagnose

### Foutmelding: "ModuleNotFoundError: No module named 'save_section_content'"
**Oorzaak**: Niet in de juiste virtuele omgeving
**Oplossing**: 
```powershell
.\venv_lokaal\Scripts\Activate.ps1
```

### Foutmelding: "❌ Niet in venv_lokaal!"
**Oorzaak**: PowerShell sessie niet in de juiste venv
**Oplossing**: 
```powershell
.\venv_lokaal\Scripts\Activate.ps1
```

## 📋 Controle Checklist

Voordat je de server start:
- [ ] Virtuele omgeving is geactiveerd (zie `(venv_lokaal)` in prompt)
- [ ] Python pad bevat `venv_lokaal` (controleer met `where python`)
- [ ] Geen andere Python processen draaien op poort 5000

## 🛠️ Scripts Overzicht

| Script | Doel | Wanneer gebruiken |
|--------|------|------------------|
| `start_server_simple.ps1` | **AANBEVOLEN** - Eenvoudige server start | Dagelijks gebruik |
| `activate_venv.ps1` | Handmatige venv activatie | Als venv niet actief is |
| `start_server.ps1` | Complexe server manager | Alleen voor geavanceerde gebruikers |

## 💡 Tips

1. **Altijd eerst venv activeren** voordat je scripts uitvoert
2. **Gebruik `start_server_simple.ps1`** voor de meeste situaties
3. **Check je Python pad** met `where python` om te zien of je in de juiste venv zit
4. **Herstart PowerShell** als je problemen hebt met venv activatie 